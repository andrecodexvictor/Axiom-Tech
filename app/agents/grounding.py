"""Grounding checks and bounded deterministic query reformulation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from app.vectorstore.port import RetrievedChunk
from app.vectorstore.retrieval import STOP_WORDS, tokenize


MIN_LEXICAL_COVERAGE = 0.20
MIN_SEMANTIC_SCORE = 0.55


@dataclass(frozen=True)
class EvidenceGrade:
    passed: bool
    lexical_coverage: float
    best_relevance_score: float


def grade_evidence(
    question: str,
    documents: Sequence[RetrievedChunk],
    *,
    allow_semantic_only: bool = False,
) -> EvidenceGrade:
    usable = [document for document in documents if document.content.strip()]
    if not usable:
        return EvidenceGrade(False, 0.0, 0.0)
    terms = meaningful_terms(question)
    evidence_terms = set()
    for document in usable:
        evidence_terms.update(_tokens(document.content))
    matching = len(terms & evidence_terms)
    coverage = matching / max(1, len(terms))
    best_score = max(max(0.0, min(float(document.score), 1.0)) for document in usable)
    passed = coverage >= MIN_LEXICAL_COVERAGE or (
        allow_semantic_only and best_score >= MIN_SEMANTIC_SCORE
    )
    return EvidenceGrade(passed, coverage, best_score)


def deduplicate_evidence(
    documents: Iterable[RetrievedChunk], *, limit: int
) -> List[RetrievedChunk]:
    selected: List[RetrievedChunk] = []
    identifiers = set()
    content_values = set()
    for document in documents:
        content_key = re.sub(r"\s+", " ", document.content).strip().casefold()
        if not document.id or not content_key:
            continue
        if document.id in identifiers or content_key in content_values:
            continue
        identifiers.add(document.id)
        content_values.add(content_key)
        selected.append(document)
        if len(selected) >= max(1, int(limit)):
            break
    return selected


def rewrite_query(question: str, attempt: int, domain: str) -> str:
    """Create a bounded retrieval reformulation without model reasoning."""

    terms = list(dict.fromkeys(_tokens(question)))
    meaningful = [term for term in terms if len(term) > 2 and term not in STOP_WORDS]
    base = " ".join(meaningful) or question.strip()
    portuguese = bool(re.search(r"[áàâãéêíóôõúç]", question.casefold())) or bool(
        set(_tokens(question)) & {"como", "qual", "quais", "devo", "segundo"}
    )
    hints_pt = {
        "rh": ("politica beneficio", "procedimento elegibilidade"),
        "juridico": ("politica requisito", "conformidade obrigacao"),
        "api_spec": ("especificacao endpoint", "contrato requisicao resposta"),
        "engenharia": ("procedimento operacional", "runbook diretriz"),
    }
    hints_en = {
        "rh": ("policy benefit", "procedure eligibility"),
        "juridico": ("policy requirement", "compliance obligation"),
        "api_spec": ("specification endpoint", "request response contract"),
        "engenharia": ("operating procedure", "runbook guideline"),
    }
    hints = hints_pt if portuguese else hints_en
    choices = hints.get(
        domain,
        ("documentacao interna", "procedimento diretriz")
        if portuguese
        else ("internal documentation", "procedure guideline"),
    )
    suffix = choices[0] if attempt <= 1 else " ".join(choices)
    return "{0} {1}".format(base, suffix).strip()


def meaningful_terms(value: str) -> set[str]:
    return {term for term in _tokens(value) if len(term) > 2 and term not in STOP_WORDS}


def _tokens(value: str) -> List[str]:
    return tokenize(value)
