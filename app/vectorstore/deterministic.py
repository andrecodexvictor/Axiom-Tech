"""Dependency-free embeddings for explicitly selected test/development runs."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, Iterable, List

from app.vectorstore.embedding import embedding_fingerprint


class DeterministicEmbedding:
    """Hashing-vector embedding stable across processes and machines.

    It is intentionally lexical rather than pretending to be a semantic cloud
    embedding.  It gives deterministic, useful matching for policy names, terms,
    identifiers and Portuguese/English corporate vocabulary without credentials.
    """

    provider_name = "deterministic"
    model_name = "axiom-hashing-v2"

    def __init__(self, dimensions: int = 384) -> None:
        if int(dimensions) < 64:
            raise ValueError("Deterministic embedding dimensions must be at least 64")
        self.dimensions = int(dimensions)
        self.fingerprint = embedding_fingerprint(
            provider=self.provider_name,
            model=self.model_name,
            dimensions=self.dimensions,
            implementation="sha256-token-features-v2",
        )

    def embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[\wÀ-ÿ][\wÀ-ÿ._/-]*", text.lower(), flags=re.UNICODE)
        if not tokens:
            return vector
        for token in self._features(tokens):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        magnitude = math.sqrt(sum(value * value for value in vector))
        return [value / magnitude for value in vector] if magnitude else vector

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        return [self.embed(text) for text in texts]

    def status(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "dimensions": self.dimensions,
            "fingerprint": self.fingerprint,
            "mode": "test-development",
            "configured": True,
        }

    @staticmethod
    def _features(tokens: List[str]) -> Iterable[str]:
        for token in tokens:
            yield token
            # A small character feature helps diacritics and compound policy terms
            # without making unrelated words dominate exact terms.
            if len(token) >= 6:
                yield "prefix:" + token[:4]
                yield "suffix:" + token[-4:]
        for left, right in zip(tokens, tokens[1:]):
            yield "pair:" + left + "_" + right

    @staticmethod
    def similarity(left: List[float], right: List[float]) -> float:
        return sum(a * b for a, b in zip(left, right))
