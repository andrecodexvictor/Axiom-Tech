"""Factory for vector-store implementations."""

from __future__ import annotations

from app.config import Settings
from app.vectorstore.chroma import ChromaUnavailableError, ChromaVectorStore
from app.vectorstore.memory import InMemoryVectorStore
from app.vectorstore.pinecone import PineconeVectorStore
from app.vectorstore.port import VectorStorePort


def create_vector_store(configuration: Settings) -> VectorStorePort:
    if configuration.vector_backend == "pinecone":
        return PineconeVectorStore()
    if configuration.vector_backend != "chroma":
        return InMemoryVectorStore("Unknown AXIOM_VECTOR_BACKEND: {0}".format(configuration.vector_backend))
    try:
        return ChromaVectorStore(configuration.chroma_path, configuration.chroma_collection)
    except ChromaUnavailableError as exc:
        return InMemoryVectorStore(str(exc))
