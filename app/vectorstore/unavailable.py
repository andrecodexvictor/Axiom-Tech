"""Fail-closed vector-store state for missing or invalid runtime configuration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.vectorstore.port import RetrievedChunk, UpsertResult, VectorStorePort


class UnavailableVectorStore(VectorStorePort):
    backend_name = "unavailable"

    def __init__(
        self,
        *,
        collection_name: str,
        reason_code: str,
        embedding_status: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.collection_name = collection_name
        self.reason_code = reason_code
        self.embedding_status = embedding_status or {
            "provider": "disabled",
            "model": "",
            "dimensions": 0,
            "fingerprint": "",
            "mode": "disabled",
            "configured": False,
        }

    def upsert(self, chunks: List[Dict[str, Any]]) -> UpsertResult:
        raise RuntimeError("Vector retrieval is unavailable ({0})".format(self.reason_code))

    def search(
        self, query: str, domain: Optional[str] = None, limit: int = 4
    ) -> List[RetrievedChunk]:
        raise RuntimeError("Vector retrieval is unavailable ({0})".format(self.reason_code))

    def status(self) -> Dict[str, Any]:
        return {
            "backend": self.backend_name,
            "collection": self.collection_name,
            "physical_collection": "",
            "document_count": 0,
            "reason": self.reason_code,
            "embedding": dict(self.embedding_status),
            "retrieval": {},
        }
