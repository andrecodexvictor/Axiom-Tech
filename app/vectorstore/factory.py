"""Factory for vector-store implementations."""

from __future__ import annotations

from app.config import Settings
from app.vectorstore.chroma import ChromaUnavailableError, ChromaVectorStore
from app.vectorstore.embedding import EmbeddingConfigurationError, create_embedding
from app.vectorstore.memory import InMemoryVectorStore
from app.vectorstore.pinecone import PineconeVectorStore
from app.vectorstore.port import VectorStorePort
from app.vectorstore.retrieval import RetrievalPolicy
from app.vectorstore.unavailable import UnavailableVectorStore


def create_vector_store(configuration: Settings) -> VectorStorePort:
    if configuration.vector_backend == "pinecone":
        return PineconeVectorStore()
    if configuration.vector_backend != "chroma":
        return UnavailableVectorStore(
            collection_name=configuration.chroma_collection,
            reason_code="unsupported_vector_backend",
        )
    retrieval_policy = RetrievalPolicy.from_configuration(configuration)
    try:
        embedding = create_embedding(configuration)
    except EmbeddingConfigurationError:
        return UnavailableVectorStore(
            collection_name=configuration.chroma_collection,
            reason_code="embedding_not_configured",
        )
    try:
        return ChromaVectorStore(
            configuration.chroma_path,
            configuration.chroma_collection,
            embedding,
            retrieval_policy,
        )
    except ChromaUnavailableError as exc:
        return InMemoryVectorStore(embedding, retrieval_policy, str(exc))
