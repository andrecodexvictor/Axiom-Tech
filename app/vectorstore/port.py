"""Ports and value objects for vector retrieval implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    content: str
    metadata: Dict[str, Any]
    score: float

    def citation(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": str(self.metadata.get("source", "unknown")),
            "domain": str(self.metadata.get("domain", "unknown")),
            "file_type": str(self.metadata.get("file_type", "")),
            "chunk_id": str(self.metadata.get("chunk_id", self.id)),
            "chunk_index": _safe_int(self.metadata.get("chunk_index", 0)),
            "score": round(float(self.score), 4),
            "path": str(self.metadata.get("path", "")),
            **(
                {"page": _safe_int(self.metadata["page"])}
                if self.metadata.get("page") is not None
                else {}
            ),
            **(
                {"slide": _safe_int(self.metadata["slide"])}
                if self.metadata.get("slide") is not None
                else {}
            ),
            **({"sheet": str(self.metadata["sheet"])} if self.metadata.get("sheet") else {}),
        }


@dataclass(frozen=True)
class UpsertResult:
    received: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0

    def __add__(self, other: "UpsertResult") -> "UpsertResult":
        return UpsertResult(
            received=self.received + other.received,
            inserted=self.inserted + other.inserted,
            updated=self.updated + other.updated,
            unchanged=self.unchanged + other.unchanged,
            removed=self.removed + other.removed,
        )


class VectorStorePort(Protocol):
    """The retrieval boundary used by ingestion and the agent graph."""

    backend_name: str

    def upsert(self, chunks: List[Dict[str, Any]], *, force: bool = False) -> UpsertResult:
        ...

    def search(
        self, query: str, domain: Optional[str] = None, limit: int = 4
    ) -> List[RetrievedChunk]:
        ...

    def status(self) -> Dict[str, Any]:
        ...
