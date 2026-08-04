"""Small offline fallback used only if Chroma cannot be imported/started."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.vectorstore.deterministic import DeterministicEmbedding
from app.vectorstore.port import RetrievedChunk, UpsertResult, VectorStorePort


class InMemoryVectorStore(VectorStorePort):
    """Non-persistent diagnostic fallback; never advertised as Chroma success."""

    backend_name = "memory-fallback"

    def __init__(self, reason: str = "Chroma unavailable") -> None:
        self.reason = reason
        self.embedding = DeterministicEmbedding()
        self._chunks: Dict[str, Dict[str, Any]] = {}

    def upsert(self, chunks: List[Dict[str, Any]]) -> UpsertResult:
        inserted = updated = unchanged = 0
        source_to_current: Dict[str, set[str]] = {}
        for chunk in chunks:
            identifier = str(chunk.get("id") or chunk.get("metadata", {}).get("chunk_id") or "")
            content = str(chunk.get("content", "")).strip()
            if not identifier or not content:
                continue
            metadata = dict(chunk.get("metadata", {}))
            source_to_current.setdefault(str(metadata.get("source_key", "")), set()).add(identifier)
            candidate = {"content": content, "metadata": metadata, "embedding": self.embedding.embed(content)}
            prior = self._chunks.get(identifier)
            if prior is None:
                inserted += 1
                self._chunks[identifier] = candidate
            elif prior["content"] == content and prior["metadata"] == metadata:
                unchanged += 1
            else:
                updated += 1
                self._chunks[identifier] = candidate
        removed = 0
        for source, current_ids in source_to_current.items():
            if source:
                stale = [
                    identifier
                    for identifier, value in self._chunks.items()
                    if str(value["metadata"].get("source_key", "")) == source and identifier not in current_ids
                ]
                for identifier in stale:
                    del self._chunks[identifier]
                removed += len(stale)
        return UpsertResult(len(chunks), inserted, updated, unchanged, removed)

    def search(
        self, query: str, domain: Optional[str] = None, limit: int = 4
    ) -> List[RetrievedChunk]:
        query_embedding = self.embedding.embed(query)
        matches = []
        for identifier, chunk in self._chunks.items():
            metadata = chunk["metadata"]
            if domain and metadata.get("domain") != domain:
                continue
            score = self.embedding.similarity(query_embedding, chunk["embedding"])
            if score > 0:
                matches.append(
                    RetrievedChunk(identifier, chunk["content"], dict(metadata), max(0.0, min(1.0, score)))
                )
        return sorted(matches, key=lambda result: (-result.score, result.id))[: max(1, int(limit))]

    def status(self) -> Dict[str, Any]:
        return {
            "backend": self.backend_name,
            "collection": "in-memory",
            "document_count": len(self._chunks),
            "reason": self.reason,
        }
