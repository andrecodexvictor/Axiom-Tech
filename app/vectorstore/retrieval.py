"""Candidate expansion, lexical reranking, thresholds, and bounded diversity."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.vectorstore.port import RetrievedChunk


STOP_WORDS = {
    "a", "an", "and", "as", "at", "como", "da", "das", "de", "do", "dos", "e",
    "are", "do", "does", "em", "for", "how", "is", "na", "nas", "no", "nos", "o",
    "of", "on", "or", "os", "our", "para", "por", "qual", "que", "the", "to", "um",
    "uma", "we", "what", "with", "é",
}


@dataclass(frozen=True)
class RetrievalPolicy:
    """Safe bounds for vector candidate retrieval and post-retrieval ranking."""

    candidate_multiplier: int = 4
    min_score: float = 0.12
    lexical_weight: float = 0.25
    mmr_lambda: float = 0.75

    @classmethod
    def from_configuration(cls, configuration: Any) -> "RetrievalPolicy":
        return cls(
            candidate_multiplier=max(
                1, min(int(getattr(configuration, "retrieval_candidate_multiplier", 4)), 10)
            ),
            min_score=max(
                0.0, min(float(getattr(configuration, "retrieval_min_score", 0.12)), 1.0)
            ),
            lexical_weight=max(
                0.0,
                min(float(getattr(configuration, "retrieval_lexical_weight", 0.25)), 0.5),
            ),
            mmr_lambda=max(
                0.5, min(float(getattr(configuration, "retrieval_mmr_lambda", 0.75)), 1.0)
            ),
        )

    def candidate_limit(self, requested: int) -> int:
        return max(1, min(max(1, int(requested)) * self.candidate_multiplier, 100))

    def status(self) -> Dict[str, Any]:
        return {
            "strategy": "vector-candidates+lexical-rerank+mmr",
            "candidate_multiplier": self.candidate_multiplier,
            "min_score": self.min_score,
            "lexical_weight": self.lexical_weight,
            "mmr_lambda": self.mmr_lambda,
        }


@dataclass(frozen=True)
class RetrievalCandidate:
    chunk: RetrievedChunk
    embedding: Optional[Sequence[float]] = None


@dataclass(frozen=True)
class _ScoredCandidate:
    candidate: RetrievalCandidate
    relevance: float
    terms: frozenset[str]


def rerank_candidates(
    query: str,
    candidates: Iterable[RetrievalCandidate],
    *,
    limit: int,
    policy: RetrievalPolicy,
) -> List[RetrievedChunk]:
    """Rerank vector candidates and select diverse chunks with a fixed bound.

    This is deliberately not called hybrid search: there is no independent
    lexical index.  Lexical evidence only reranks the expanded vector candidate
    set, then an MMR-style selection reduces near-duplicate chunks.
    """

    query_terms = _meaningful_terms(query)
    scored: List[_ScoredCandidate] = []
    seen_ids = set()
    seen_content = set()
    for candidate in candidates:
        chunk = candidate.chunk
        if chunk.id in seen_ids:
            continue
        content_key = re.sub(r"\s+", " ", chunk.content).strip().casefold()
        if not content_key or content_key in seen_content:
            continue
        seen_ids.add(chunk.id)
        seen_content.add(content_key)
        document_terms = frozenset(_tokens(chunk.content))
        lexical = _lexical_score(query_terms, document_terms)
        vector_score = max(0.0, min(float(chunk.score), 1.0))
        relevance = (1.0 - policy.lexical_weight) * vector_score + policy.lexical_weight * lexical
        if math.isfinite(relevance) and relevance >= policy.min_score:
            scored.append(_ScoredCandidate(candidate, relevance, document_terms))

    remaining = sorted(
        scored,
        key=lambda item: (-item.relevance, item.candidate.chunk.id),
    )
    selected: List[_ScoredCandidate] = []
    requested = max(1, int(limit))
    while remaining and len(selected) < requested:
        if not selected:
            choice = remaining[0]
        else:
            choice = max(
                remaining,
                key=lambda item: (
                    _mmr_value(item, selected, policy.mmr_lambda),
                    item.relevance,
                    _source_novelty(item, selected),
                    item.candidate.chunk.id,
                ),
            )
        selected.append(choice)
        remaining.remove(choice)

    return [
        RetrievedChunk(
            id=item.candidate.chunk.id,
            content=item.candidate.chunk.content,
            metadata=dict(item.candidate.chunk.metadata),
            score=round(item.relevance, 6),
        )
        for item in selected
    ]


def _mmr_value(
    item: _ScoredCandidate, selected: Sequence[_ScoredCandidate], mmr_lambda: float
) -> float:
    redundancy = max(_candidate_similarity(item, prior) for prior in selected)
    return mmr_lambda * item.relevance - (1.0 - mmr_lambda) * redundancy


def _candidate_similarity(left: _ScoredCandidate, right: _ScoredCandidate) -> float:
    left_vector = left.candidate.embedding
    right_vector = right.candidate.embedding
    if left_vector is not None and right_vector is not None and len(left_vector) == len(right_vector):
        try:
            similarity = sum(float(a) * float(b) for a, b in zip(left_vector, right_vector))
            if math.isfinite(similarity):
                return max(0.0, min(similarity, 1.0))
        except (TypeError, ValueError):
            pass
    union = left.terms | right.terms
    return len(left.terms & right.terms) / len(union) if union else 0.0


def _source_novelty(item: _ScoredCandidate, selected: Sequence[_ScoredCandidate]) -> int:
    source = str(item.candidate.chunk.metadata.get("source_key", ""))
    return int(bool(source) and all(
        str(prior.candidate.chunk.metadata.get("source_key", "")) != source
        for prior in selected
    ))


def _lexical_score(query_terms: frozenset[str], document_terms: frozenset[str]) -> float:
    if not query_terms or not document_terms:
        return 0.0
    overlap = len(query_terms & document_terms)
    coverage = overlap / len(query_terms)
    # Precision is capped to a query-sized window so long chunks are not unfairly
    # punished while exact identifiers still receive a useful boost.
    precision = overlap / max(1, min(len(document_terms), len(query_terms) * 4))
    return min(1.0, 0.85 * coverage + 0.15 * precision)


def _meaningful_terms(value: str) -> frozenset[str]:
    return frozenset(token for token in _tokens(value) if len(token) > 2 and token not in STOP_WORDS)


def _tokens(value: str) -> List[str]:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.findall(r"[a-z0-9][a-z0-9._/-]*", normalized)
