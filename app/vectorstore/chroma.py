"""Persistent Chroma implementation of the vector-store port."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Sequence

from app.vectorstore.embedding import EMBEDDING_CONTRACT_VERSION, EmbeddingPort
from app.vectorstore.port import RetrievedChunk, UpsertResult, VectorStorePort
from app.vectorstore.retrieval import RetrievalCandidate, RetrievalPolicy, rerank_candidates


class ChromaUnavailableError(RuntimeError):
    """Raised when the optional Chroma package cannot be initialized."""


class EmbeddingCollectionMismatch(RuntimeError):
    """Raised rather than mixing incompatible vectors in one collection."""


def _primitive_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            result[str(key)] = value
        else:
            result[str(key)] = str(value)
    return result


class ChromaVectorStore(VectorStorePort):
    """Chroma persistence with injected embeddings and collection versioning."""

    backend_name = "chroma"

    def __init__(
        self,
        persist_path: Path,
        collection_name: str,
        embedding: EmbeddingPort,
        retrieval_policy: RetrievalPolicy,
    ) -> None:
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ImportError as exc:
            raise ChromaUnavailableError("chromadb is not installed") from exc

        self.persist_path = Path(persist_path)
        self.persist_path.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self.embedding = embedding
        self.retrieval_policy = retrieval_policy
        self.physical_collection_name = self._versioned_collection_name(
            collection_name, embedding.fingerprint
        )
        collection_metadata: Dict[str, Any] = {
            "hnsw:space": "cosine",
            "axiom:embedding_contract": EMBEDDING_CONTRACT_VERSION,
            "axiom:embedding_fingerprint": embedding.fingerprint,
            "axiom:embedding_provider": embedding.provider_name,
            "axiom:embedding_model": embedding.model_name,
            "axiom:embedding_dimensions": embedding.dimensions,
        }
        try:
            self._client = chromadb.PersistentClient(
                path=str(self.persist_path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.physical_collection_name,
                metadata=collection_metadata,
                embedding_function=None,
            )
            self._validate_collection_metadata(collection_metadata)
        except Exception as exc:  # pragma: no cover - version/platform specific Chroma failure
            if isinstance(exc, EmbeddingCollectionMismatch):
                raise
            raise ChromaUnavailableError("Could not initialize persistent Chroma: {0}".format(exc)) from exc

    def upsert(self, chunks: List[Dict[str, Any]]) -> UpsertResult:
        if not chunks:
            return UpsertResult()
        normalized = [self._normalize_chunk(chunk) for chunk in chunks]
        existing = self._get_by_ids([chunk["id"] for chunk in normalized])
        existing_by_id = {
            identifier: (document, metadata)
            for identifier, document, metadata in zip(
                existing.get("ids", []), existing.get("documents", []), existing.get("metadatas", [])
            )
        }
        to_write: List[Dict[str, Any]] = []
        inserted = updated = unchanged = 0
        for chunk in normalized:
            prior = existing_by_id.get(chunk["id"])
            if prior is None:
                inserted += 1
                to_write.append(chunk)
            elif prior[0] == chunk["content"] and dict(prior[1] or {}) == chunk["metadata"]:
                unchanged += 1
            else:
                updated += 1
                to_write.append(chunk)

        # Resolve and validate every vector before deleting stale source chunks.
        # A remote embedding outage therefore cannot erase the last usable copy.
        write_embeddings = (
            self.embedding.embed_many(chunk["content"] for chunk in to_write)
            if to_write
            else []
        )
        if len(write_embeddings) != len(to_write):
            raise RuntimeError("Embedding provider returned an incomplete upsert batch")

        # A changed source produces new content-addressed ids.  Remove old chunks
        # for that source before writing the replacement to prevent stale answers.
        removed = 0
        by_source: DefaultDict[str, set[str]] = defaultdict(set)
        for chunk in normalized:
            by_source[str(chunk["metadata"].get("source_key", ""))].add(chunk["id"])
        for source_key, current_ids in by_source.items():
            if not source_key:
                continue
            old_ids = set(self._ids_for_source(source_key))
            stale_ids = list(old_ids - current_ids)
            if stale_ids:
                self._collection.delete(ids=stale_ids)
                removed += len(stale_ids)

        if to_write:
            self._upsert_many(to_write, write_embeddings)
        return UpsertResult(
            received=len(normalized),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            removed=removed,
        )

    def search(
        self, query: str, domain: Optional[str] = None, limit: int = 4
    ) -> List[RetrievedChunk]:
        if not query.strip() or self._collection.count() == 0:
            return []
        options: Dict[str, Any] = {
            "query_embeddings": [self.embedding.embed(query)],
            "n_results": min(
                self._collection.count(), self.retrieval_policy.candidate_limit(limit)
            ),
            "include": ["documents", "metadatas", "distances", "embeddings"],
        }
        if domain:
            options["where"] = {"domain": domain}
        response = self._collection.query(**options)
        ids = (response.get("ids") or [[]])[0]
        documents = (response.get("documents") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        raw_embeddings = response.get("embeddings")
        embeddings = raw_embeddings[0] if raw_embeddings is not None and len(raw_embeddings) else []
        results: List[RetrievalCandidate] = []
        for index, (identifier, document, metadata, distance) in enumerate(
            zip(ids, documents, metadatas, distances)
        ):
            # Cosine distance is 1 - similarity.  Clamp guards against minute
            # numeric drift without overstating relevance.
            score = max(0.0, min(1.0, 1.0 - float(distance)))
            candidate_embedding = embeddings[index] if index < len(embeddings) else None
            results.append(
                RetrievalCandidate(
                    RetrievedChunk(
                        id=str(identifier),
                        content=str(document or ""),
                        metadata=dict(metadata or {}),
                        score=score,
                    ),
                    embedding=candidate_embedding,
                )
            )
        return rerank_candidates(
            query,
            results,
            limit=max(1, int(limit)),
            policy=self.retrieval_policy,
        )

    def status(self) -> Dict[str, Any]:
        return {
            "backend": self.backend_name,
            "collection": self.collection_name,
            "physical_collection": self.physical_collection_name,
            "document_count": self._collection.count(),
            "persist_path": str(self.persist_path),
            "embedding": self.embedding.status(),
            "retrieval": self.retrieval_policy.status(),
        }

    def _validate_collection_metadata(self, expected: Dict[str, Any]) -> None:
        actual = dict(getattr(self._collection, "metadata", {}) or {})
        protected_keys = (
            "axiom:embedding_contract",
            "axiom:embedding_fingerprint",
            "axiom:embedding_provider",
            "axiom:embedding_model",
            "axiom:embedding_dimensions",
        )
        if any(str(actual.get(key, "")) != str(expected[key]) for key in protected_keys):
            raise EmbeddingCollectionMismatch(
                "The Chroma collection belongs to a different embedding vector space"
            )

    @staticmethod
    def _versioned_collection_name(collection_name: str, fingerprint: str) -> str:
        # Chroma names are limited to 63 characters and must begin/end with an
        # alphanumeric character.  A fingerprint suffix makes model upgrades
        # create a new collection instead of mixing incompatible vectors.
        base = re.sub(r"[^A-Za-z0-9._-]+", "-", collection_name).strip("._-")
        base = base or "axiom-knowledge"
        base = base[:46].rstrip("._-") or "axiom"
        return "{0}-{1}".format(base, fingerprint[:12])

    def _get_by_ids(self, ids: Sequence[str]) -> Dict[str, Any]:
        if not ids:
            return {"ids": [], "documents": [], "metadatas": []}
        return self._collection.get(ids=list(ids), include=["documents", "metadatas"])

    def _ids_for_source(self, source_key: str) -> Iterable[str]:
        # Older Chroma releases validate ``include`` against a non-empty enum, so
        # request only metadata even though ids are the sole value we need.
        response = self._collection.get(where={"source_key": source_key}, include=["metadatas"])
        return response.get("ids", [])

    def _upsert_many(
        self, chunks: List[Dict[str, Any]], embeddings: List[List[float]]
    ) -> None:
        # Chroma accepts batches, but modest batches also avoid request-size issues
        # for large PDFs and decks.
        for start in range(0, len(chunks), 128):
            batch = chunks[start : start + 128]
            embedding_batch = embeddings[start : start + 128]
            self._collection.upsert(
                ids=[chunk["id"] for chunk in batch],
                documents=[chunk["content"] for chunk in batch],
                metadatas=[chunk["metadata"] for chunk in batch],
                embeddings=embedding_batch,
            )

    @staticmethod
    def _normalize_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
        identifier = str(chunk.get("id") or chunk.get("metadata", {}).get("chunk_id") or "")
        content = str(chunk.get("content", "")).strip()
        if not identifier or not content:
            raise ValueError("Each vector chunk needs a stable id and non-empty content")
        metadata = _primitive_metadata(dict(chunk.get("metadata", {})))
        metadata.setdefault("chunk_id", identifier)
        return {"id": identifier, "content": content, "metadata": metadata}
