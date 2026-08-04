"""Legacy import compatibility for the former ``vector_store`` singleton.

New application code uses ``create_vector_store`` and injects the port.  This
wrapper retains the old methods for command-line/import callers while avoiding the
previous fake Pinecone success message.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import settings
from app.vectorstore.factory import create_vector_store


class VectorStore:
    def __init__(self) -> None:
        self._delegate = create_vector_store(settings)

    def index_documents(self, chunks: List[Dict[str, Any]]) -> int:
        return self._delegate.upsert(chunks).inserted

    def similarity_search(
        self, query: str, domain_filter: Optional[str] = None, top_k: int = 4
    ) -> List[Dict[str, Any]]:
        return [
            {"id": result.id, "content": result.content, "metadata": result.metadata, "score": result.score}
            for result in self._delegate.search(query, domain_filter, top_k)
        ]

    def status(self) -> Dict[str, Any]:
        return self._delegate.status()


vector_store = VectorStore()
