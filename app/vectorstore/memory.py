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
from app.vectorstore.upsert import build_upsert_plan


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
        plan = build_upsert_plan(
            normalized,
            self._chunks,
            force=force,
            is_unchanged=lambda prior, chunk: (
                prior["content"] == chunk["content"]
                and prior["metadata"] == chunk["metadata"]
            ),
        )
        if plan.to_write:
            embeddings = self.embedding.embed_many(
                item["content"] for item in plan.to_write
            )
            if len(embeddings) != len(plan.to_write):
                raise RuntimeError("Embedding provider returned an incomplete upsert batch")
            for chunk, embedding in zip(plan.to_write, embeddings):
                self._chunks[chunk["id"]] = {
                    "content": chunk["content"],
                    "metadata": chunk["metadata"],
                    "embedding": embedding,
                }
        removed = self._delete_stale_chunks(plan.current_ids_by_source)
        return UpsertResult(
            len(normalized),
            plan.inserted,
            plan.updated,
            plan.unchanged,
            removed,
        )

    def _delete_stale_chunks(self, current_ids_by_source: Dict[str, set[str]]) -> int:
        removed = 0
        for source, current_ids in current_ids_by_source.items():
            if not source:
                continue
            stale = [
                identifier
                for identifier, value in self._chunks.items()
                if str(value["metadata"].get("source_key", "")) == source
                and identifier not in current_ids
            ]
            for identifier in stale:
                del self._chunks[identifier]
            removed += len(stale)
        return removed

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
