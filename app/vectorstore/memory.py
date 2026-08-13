"""Non-persistent fallback that preserves the configured embedding contract."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.vectorstore.embedding import EmbeddingPort, cosine_similarity
from app.vectorstore.port import RetrievedChunk, UpsertResult, VectorStorePort
from app.vectorstore.retrieval import (
    RetrievalCandidate,
    RetrievalPolicy,
    rerank_candidates,
)


class InMemoryVectorStore(VectorStorePort):
    """Non-persistent diagnostic fallback; never advertised as Chroma success."""

    backend_name = "memory-fallback"

    def __init__(
        self,
        embedding: EmbeddingPort,
        retrieval_policy: RetrievalPolicy,
        reason: str = "Chroma unavailable",
    ) -> None:
        self.reason = reason
        self.embedding = embedding
        self.retrieval_policy = retrieval_policy
        self._chunks: Dict[str, Dict[str, Any]] = {}

    def upsert(self, chunks: List[Dict[str, Any]], *, force: bool = False) -> UpsertResult:
        normalized = [self._normalize_chunk(chunk) for chunk in chunks]
        inserted = updated = unchanged = 0
        source_to_current: Dict[str, set[str]] = {}
        to_write: List[Dict[str, Any]] = []
        for chunk in normalized:
            identifier = chunk["id"]
            content = chunk["content"]
            metadata = chunk["metadata"]
            source_to_current.setdefault(str(metadata.get("source_key", "")), set()).add(identifier)
            prior = self._chunks.get(identifier)
            if prior is None:
                inserted += 1
                to_write.append(chunk)
            elif not force and prior["content"] == content and prior["metadata"] == metadata:
                unchanged += 1
            else:
                updated += 1
                to_write.append(chunk)
        if to_write:
            embeddings = self.embedding.embed_many(item["content"] for item in to_write)
            if len(embeddings) != len(to_write):
                raise RuntimeError("Embedding provider returned an incomplete upsert batch")
            for chunk, embedding in zip(to_write, embeddings):
                self._chunks[chunk["id"]] = {
                    "content": chunk["content"],
                    "metadata": chunk["metadata"],
                    "embedding": embedding,
                }
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
        return UpsertResult(len(normalized), inserted, updated, unchanged, removed)

    def source_inventory(self) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for value in self._chunks.values():
            metadata = value["metadata"]
            source_key = str(metadata.get("source_key", ""))
            if not source_key:
                continue
            item = grouped.setdefault(
                source_key,
                {
                    "source_key": source_key,
                    "source": str(metadata.get("source", source_key)),
                    "domain": str(metadata.get("domain", "unknown")),
                    "file_type": str(metadata.get("file_type", "")),
                    "size_bytes": metadata.get("size_bytes"),
                    "modified_ns": metadata.get("modified_ns"),
                    "chunks": 0,
                    "document_hashes": set(),
                },
            )
            item["chunks"] += 1
            document_hash = str(metadata.get("document_hash", ""))
            if document_hash:
                item["document_hashes"].add(document_hash)
        return [
            {**item, "document_hashes": sorted(item["document_hashes"])}
            for item in grouped.values()
        ]

    def search(
        self, query: str, domain: Optional[str] = None, limit: int = 4
    ) -> List[RetrievedChunk]:
        if not query.strip():
            return []
        query_embedding = self.embedding.embed(query)
        matches: List[RetrievalCandidate] = []
        for identifier, chunk in self._chunks.items():
            metadata = chunk["metadata"]
            if domain and metadata.get("domain") != domain:
                continue
            score = cosine_similarity(query_embedding, chunk["embedding"])
            if score > 0.0:
                matches.append(
                    RetrievalCandidate(
                        RetrievedChunk(
                            identifier,
                            chunk["content"],
                            dict(metadata),
                            max(0.0, min(1.0, score)),
                        ),
                        embedding=chunk["embedding"],
                    )
                )
        candidates = sorted(
            matches,
            key=lambda candidate: (-candidate.chunk.score, candidate.chunk.id),
        )[: self.retrieval_policy.candidate_limit(limit)]
        return rerank_candidates(
            query,
            candidates,
            limit=max(1, int(limit)),
            policy=self.retrieval_policy,
        )

    def status(self) -> Dict[str, Any]:
        source_count = len(
            {
                str(value["metadata"].get("source_key", ""))
                for value in self._chunks.values()
                if value["metadata"].get("source_key")
            }
        )
        return {
            "backend": self.backend_name,
            "collection": "in-memory",
            "physical_collection": "in-memory",
            "document_count": len(self._chunks),
            "source_count": source_count,
            "reason": self.reason,
            "embedding": self.embedding.status(),
            "retrieval": self.retrieval_policy.status(),
        }

    @staticmethod
    def _normalize_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
        identifier = str(chunk.get("id") or chunk.get("metadata", {}).get("chunk_id") or "")
        content = str(chunk.get("content", "")).strip()
        if not identifier or not content:
            raise ValueError("Each vector chunk needs a stable id and non-empty content")
        metadata = dict(chunk.get("metadata", {}))
        metadata.setdefault("chunk_id", identifier)
        return {"id": identifier, "content": content, "metadata": metadata}
