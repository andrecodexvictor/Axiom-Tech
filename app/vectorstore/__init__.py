"""Vector-store adapters and public factory."""

from app.vectorstore.factory import create_vector_store
from app.vectorstore.port import RetrievedChunk, UpsertResult, VectorStorePort

__all__ = ["RetrievedChunk", "UpsertResult", "VectorStorePort", "create_vector_store"]
