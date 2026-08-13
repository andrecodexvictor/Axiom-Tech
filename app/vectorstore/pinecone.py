"""Optional Pinecone boundary.

This intentionally does not claim an upsert succeeded.  A deployment that selects
Pinecone must provide a production adapter with index dimensions, namespace and
credential policy; otherwise the application fails clearly rather than silently
indexing nowhere.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.vectorstore.port import RetrievedChunk, UpsertResult, VectorStorePort


class PineconeVectorStore(VectorStorePort):
    backend_name = "pinecone-unconfigured"

    def __init__(self, message: str = "Pinecone adapter is not configured for this deployment") -> None:
        self.message = message

    def upsert(self, chunks: List[Dict[str, Any]], *, force: bool = False) -> UpsertResult:
        del chunks, force
        raise RuntimeError(self.message)

    def search(
        self, query: str, domain: Optional[str] = None, limit: int = 4
    ) -> List[RetrievedChunk]:
        raise RuntimeError(self.message)

    def status(self) -> Dict[str, Any]:
        return {
            "backend": self.backend_name,
            "collection": "",
            "document_count": 0,
            "source_count": 0,
            "reason": self.message,
        }

    def source_inventory(self) -> List[Dict[str, Any]]:
        return []
