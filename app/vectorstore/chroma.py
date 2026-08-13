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
        # A single-process API repeatedly upserts files during one explicit
        # ingestion pass.  Keep only IDs and metadata locally.  Content is
        # already persisted by Chroma and is not needed for change detection:
        # current chunks carry a content_hash.  Avoiding a full document cache is
        # important on small VMs because corpus text can be much larger than the
        # metadata needed for indexing decisions.
        self._chunk_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._source_ids_cache: Optional[DefaultDict[str, set[str]]] = None
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

    def upsert(self, chunks: List[Dict[str, Any]], *, force: bool = False) -> UpsertResult:
        if not chunks:
            return UpsertResult()
        normalized = [self._normalize_chunk(chunk) for chunk in chunks]
        existing = self._get_by_ids([chunk["id"] for chunk in normalized])
        existing_by_id = {
            identifier: metadata
            for identifier, metadata in zip(
                existing.get("ids", []), existing.get("metadatas", [])
            )
        }
        to_write: List[Dict[str, Any]] = []
        inserted = updated = unchanged = 0
        for chunk in normalized:
            prior = existing_by_id.get(chunk["id"])
            if prior is None:
                inserted += 1
                to_write.append(chunk)
            elif (
                not force
                and self._same_metadata(prior, chunk["metadata"])
            ):
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
                if self._chunk_cache is not None:
                    for stale_id in stale_ids:
                        self._chunk_cache.pop(stale_id, None)
                if self._source_ids_cache is not None:
                    self._source_ids_cache[source_key].difference_update(stale_ids)
                removed += len(stale_ids)

        if to_write:
            self._upsert_many(to_write, write_embeddings)
            if self._chunk_cache is not None and self._source_ids_cache is not None:
                for chunk in to_write:
                    identifier = chunk["id"]
                    source_key = str(chunk["metadata"].get("source_key", ""))
                    self._chunk_cache[identifier] = chunk["metadata"]
                    if source_key:
                        self._source_ids_cache[source_key].add(identifier)
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
        collection_count = self._collection.count()
        if not query.strip() or collection_count == 0:
            return []
        options: Dict[str, Any] = {
            "query_embeddings": [self.embedding.embed(query)],
            "n_results": min(
                collection_count, self.retrieval_policy.candidate_limit(limit)
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
        source_count: Optional[int] = None
        if hasattr(self._collection, "get"):
            try:
                # Status is polled frequently by the console.  Populate the
                # metadata-only cache once instead of allocating a fresh full
                # metadatas response on every poll.
                self._ensure_cache()
                source_count = len(
                    [source for source, ids in (self._source_ids_cache or {}).items() if ids]
                )
            except Exception:
                # Keep compatibility with older/fake Chroma clients.
                source_count = None
        return {
            "backend": self.backend_name,
            "collection": self.collection_name,
            "physical_collection": self.physical_collection_name,
            "document_count": self._collection.count(),
            "source_count": source_count,
            "persist_path": str(self.persist_path),
            "embedding": self.embedding.status(),
            "retrieval": self.retrieval_policy.status(),
        }

    def source_inventory(self) -> List[Dict[str, Any]]:
        self._ensure_cache()
        grouped: Dict[str, Dict[str, Any]] = {}
        for metadata in (self._chunk_cache or {}).values():
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
        self._ensure_cache()
        cache = self._chunk_cache or {}
        existing_ids = [identifier for identifier in ids if identifier in cache]
        return {
            "ids": existing_ids,
            "metadatas": [cache[identifier] for identifier in existing_ids],
        }

    def _ids_for_source(self, source_key: str) -> Iterable[str]:
        self._ensure_cache()
        return (self._source_ids_cache or {}).get(source_key, set())

    def _ensure_cache(self) -> None:
        if self._chunk_cache is not None and self._source_ids_cache is not None:
            return
        self._chunk_cache = {}
        self._source_ids_cache = defaultdict(set)
        if not hasattr(self._collection, "get"):
            return
        # Chroma always returns ids; metadata is enough for idempotent writes,
        # stale-source cleanup, and the source inventory.  Do not pull document
        # bodies into the Python process.
        response = self._collection.get(include=["metadatas"])
        ids = response.get("ids", [])
        metadatas = response.get("metadatas", [])
        for identifier, metadata in zip(ids, metadatas):
            normalized_id = str(identifier)
            normalized_metadata = dict(metadata or {})
            self._chunk_cache[normalized_id] = normalized_metadata
            source_key = str(normalized_metadata.get("source_key", ""))
            if source_key:
                self._source_ids_cache[source_key].add(normalized_id)

    @staticmethod
    def _same_metadata(prior: Dict[str, Any], current: Dict[str, Any]) -> bool:
        """Compare metadata without retaining or reading persisted document text.

        Collections created before ``content_hash`` was added are treated as
        changed once, which safely upgrades their records during ingestion.
        """

        return bool(prior.get("content_hash")) and dict(prior) == dict(current)

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
