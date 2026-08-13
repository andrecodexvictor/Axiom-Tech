from __future__ import annotations

from dataclasses import replace
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys

import pytest

from app.graph import AxiomAgentGraph
from app.agents.grounding import grade_evidence
from app.ingestion.chunker import DocumentChunker
from app.ingestion.loader import DocumentLoader
from app.llm_client import ModelGateway
from app.service import create_knowledge_service
from app.vectorstore.chroma import ChromaVectorStore, EmbeddingCollectionMismatch
from app.vectorstore.deterministic import DeterministicEmbedding
from app.vectorstore.embedding import EmbeddingResponseError, OpenAICompatibleEmbedding
from app.vectorstore.factory import create_vector_store
from app.vectorstore.memory import InMemoryVectorStore
from app.vectorstore.port import RetrievedChunk, UpsertResult
from app.vectorstore.retrieval import (
    RetrievalCandidate,
    RetrievalPolicy,
    rerank_candidates,
)


def test_remote_embedding_batches_validates_and_never_falls_back() -> None:
    calls = []

    class FakeEmbeddings:
        def create(self, **kwargs):
            calls.append(kwargs)
            records = []
            for index, _value in enumerate(kwargs["input"]):
                vector = [0.0] * kwargs["dimensions"]
                vector[index % kwargs["dimensions"]] = 2.0
                records.append(SimpleNamespace(index=index, embedding=vector))
            return SimpleNamespace(data=list(reversed(records)))

    provider = OpenAICompatibleEmbedding(
        api_key="test-only",
        model="embedding-test-model",
        dimensions=64,
        base_url="https://embeddings.example.test/v1",
        batch_size=2,
        client=SimpleNamespace(embeddings=FakeEmbeddings()),
    )

    vectors = provider.embed_many(["one", "two", "three"])

    assert len(calls) == 2
    assert len(vectors) == 3
    assert all(len(vector) == 64 for vector in vectors)
    assert all(sum(value * value for value in vector) == pytest.approx(1.0) for vector in vectors)
    assert provider.status() == {
        "provider": "openai",
        "model": "embedding-test-model",
        "dimensions": 64,
        "fingerprint": provider.fingerprint,
        "mode": "remote",
        "configured": True,
    }

    class FailingEmbeddings:
        def create(self, **_kwargs):
            raise TimeoutError("provider body must not escape")

    unavailable = OpenAICompatibleEmbedding(
        api_key="test-only",
        model="embedding-test-model",
        dimensions=64,
        base_url="https://embeddings.example.test/v1",
        client=SimpleNamespace(embeddings=FailingEmbeddings()),
    )
    with pytest.raises(EmbeddingResponseError, match="TimeoutError") as captured:
        unavailable.embed("query")
    assert "provider body" not in str(captured.value)

    class DuplicateIndexes:
        def create(self, **kwargs):
            vector = [1.0] + [0.0] * (kwargs["dimensions"] - 1)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=0, embedding=vector),
                    SimpleNamespace(index=0, embedding=vector),
                ]
            )

    malformed = OpenAICompatibleEmbedding(
        api_key="test-only",
        model="embedding-test-model",
        dimensions=64,
        base_url="https://embeddings.example.test/v1",
        client=SimpleNamespace(embeddings=DuplicateIndexes()),
    )
    with pytest.raises(EmbeddingResponseError, match="invalid indexes"):
        malformed.embed_many(["one", "two"])


def test_nemotron_retriever_uses_passage_and_query_input_types() -> None:
    calls = []

    class FakeEmbeddings:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=0, embedding=[1.0, 0.0, 0.0, 0.0])
                    for _ in kwargs["input"]
                ]
            )

    provider = OpenAICompatibleEmbedding(
        api_key="test-only",
        model="nvidia/llama-nemotron-embed-1b-v2",
        dimensions=4,
        base_url="https://integrate.api.nvidia.com/v1",
        client=SimpleNamespace(embeddings=FakeEmbeddings()),
    )

    provider.embed_many(["passage"])
    provider.embed("query")

    assert calls[0]["extra_body"] == {"input_type": "passage"}
    assert calls[1]["extra_body"] == {"input_type": "query"}


def test_disabled_embedding_is_fail_closed_and_status_is_sanitized(axiom_settings) -> None:
    configured = replace(axiom_settings, embedding_provider="disabled")

    store = create_vector_store(configured)
    status = store.status()

    assert status["backend"] == "unavailable"
    assert status["reason"] == "embedding_not_configured"
    assert status["embedding"]["configured"] is False
    with pytest.raises(RuntimeError, match="embedding_not_configured"):
        store.search("question")


def test_status_exposes_only_sanitized_embedding_and_retrieval_contract(axiom_settings) -> None:
    status = create_knowledge_service(axiom_settings).status()
    vector = status["vector_store"]

    assert vector["embedding"] == {
        "provider": "deterministic",
        "model": "axiom-hashing-v2",
        "dimensions": 384,
        "fingerprint": vector["embedding"]["fingerprint"],
        "mode": "test-development",
        "configured": True,
    }
    assert vector["retrieval"]["strategy"] == "vector-candidates+lexical-rerank+mmr"
    if vector["backend"] == "chroma":
        assert vector["physical_collection"].endswith(vector["embedding"]["fingerprint"][:12])
    else:
        assert vector["physical_collection"] == "in-memory"
    assert str(axiom_settings.documents_dir.parent) not in repr(status)


def test_memory_fallback_uses_provider_neutral_similarity() -> None:
    class FakeEmbedding:
        provider_name = "fake"
        model_name = "fake-v1"
        dimensions = 2
        fingerprint = "f" * 64

        def embed(self, text):
            return [1.0, 0.0] if "alpha" in text.casefold() else [0.0, 1.0]

        def embed_many(self, texts):
            return [self.embed(text) for text in texts]

        def status(self):
            return {
                "provider": self.provider_name,
                "model": self.model_name,
                "dimensions": self.dimensions,
                "fingerprint": self.fingerprint,
                "mode": "remote",
                "configured": True,
            }

    store = InMemoryVectorStore(FakeEmbedding(), RetrievalPolicy(), "test fallback")
    store.upsert(
        [
            {
                "id": "alpha",
                "content": "Alpha recovery procedure.",
                "metadata": {"source_key": "alpha.md"},
            }
        ]
    )

    assert [result.id for result in store.search("alpha procedure")] == ["alpha"]


def test_embedding_fingerprint_versions_chroma_and_requires_reindex(
    monkeypatch, tmp_path: Path
) -> None:
    class FakeCollection:
        def __init__(self, metadata):
            self.metadata = dict(metadata)
            self.document_count = 0

        def count(self):
            return self.document_count

    class FakeClient:
        collections = {}

        def get_or_create_collection(self, name, metadata, embedding_function):
            del embedding_function
            return self.collections.setdefault(name, FakeCollection(metadata))

    chromadb = ModuleType("chromadb")
    chromadb.PersistentClient = lambda **_kwargs: FakeClient()
    chroma_config = ModuleType("chromadb.config")
    chroma_config.Settings = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "chromadb", chromadb)
    monkeypatch.setitem(sys.modules, "chromadb.config", chroma_config)

    first_embedding = DeterministicEmbedding(384)
    upgraded_embedding = DeterministicEmbedding(512)
    policy = RetrievalPolicy()
    first = ChromaVectorStore(tmp_path, "axiom_knowledge", first_embedding, policy)
    first._collection.document_count = 7
    upgraded = ChromaVectorStore(tmp_path, "axiom_knowledge", upgraded_embedding, policy)

    assert first.physical_collection_name != upgraded.physical_collection_name
    assert first.status()["document_count"] == 7
    assert upgraded.status()["document_count"] == 0
    assert upgraded.status()["embedding"]["fingerprint"] == upgraded_embedding.fingerprint

    incompatible_name = ChromaVectorStore._versioned_collection_name(
        "collision", first_embedding.fingerprint
    )
    FakeClient.collections[incompatible_name] = FakeCollection(
        {"axiom:embedding_fingerprint": "wrong"}
    )
    with pytest.raises(EmbeddingCollectionMismatch):
        ChromaVectorStore(tmp_path, "collision", first_embedding, policy)


def test_vector_candidates_are_thresholded_lexically_reranked_and_diversified() -> None:
    policy = RetrievalPolicy(
        candidate_multiplier=4,
        min_score=0.12,
        lexical_weight=0.25,
        mmr_lambda=0.60,
    )
    candidates = [
        RetrievalCandidate(
            RetrievedChunk(
                "a", "Incident recovery procedure and quarterly drill.", {"source_key": "one"}, 0.90
            ),
            [1.0, 0.0],
        ),
        RetrievalCandidate(
            RetrievedChunk(
                "b", "Incident recovery procedure checklist.", {"source_key": "one"}, 0.80
            ),
            [0.999, 0.001],
        ),
        RetrievalCandidate(
            RetrievedChunk(
                "c", "Quarterly recovery procedure for an incident.", {"source_key": "two"}, 0.78
            ),
            [0.0, 1.0],
        ),
        RetrievalCandidate(
            RetrievedChunk("noise", "Cafeteria menu for Monday.", {"source_key": "three"}, 0.10),
            [0.0, 1.0],
        ),
    ]

    results = rerank_candidates(
        "incident recovery procedure", candidates, limit=3, policy=policy
    )

    assert [result.id for result in results[:2]] == ["a", "c"]
    assert "noise" not in [result.id for result in results]
    assert all(result.score >= policy.min_score for result in results)


def test_deterministic_grounding_requires_textual_evidence_even_with_high_score() -> None:
    irrelevant = RetrievedChunk(
        "collision",
        "The cafeteria serves soup on Tuesday.",
        {"source": "menu.md"},
        0.99,
    )

    deterministic = grade_evidence(
        "How do we rotate encryption keys?", [irrelevant], allow_semantic_only=False
    )
    semantic_provider = grade_evidence(
        "How do we rotate encryption keys?", [irrelevant], allow_semantic_only=True
    )

    assert deterministic.lexical_coverage == 0.0
    assert deterministic.passed is False
    assert semantic_provider.passed is True


def test_chunking_normalizes_text_and_preserves_stable_spans_and_metadata() -> None:
    content = (
        "# Recovery\r\n\r\n"
        + "Incident owners validate recovery procedures every quarter. " * 8
        + "\r\n\r\n## Escalation\r\nEscalate unresolved incidents to operations leadership."
    )
    chunker = DocumentChunker(chunk_size=180, chunk_overlap=35)
    document = {
        "content": content,
        "metadata": {"source": "runbook.md", "source_key": "engineering/runbook.md"},
    }

    first = chunker.split_documents([document])
    second = chunker.split_documents([document])
    normalized = chunker._normalize_text(content)

    assert len(first) > 2
    assert [chunk["id"] for chunk in first] == [chunk["id"] for chunk in second]
    assert {chunk["metadata"]["chunk_count"] for chunk in first} == {len(first)}
    assert len({chunk["metadata"]["document_id"] for chunk in first}) == 1
    for chunk in first:
        metadata = chunk["metadata"]
        assert chunk["content"] == normalized[metadata["char_start"] : metadata["char_end"]]
        assert metadata["content_hash"]
        assert metadata["word_count"] > 0


def test_loader_uses_corpus_relative_source_key(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    source = corpus / "rh" / "policy.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Policy\nRemote work is approved.", encoding="utf-8")

    document = DocumentLoader.load_file(source, source_root=corpus)[0]

    assert document["metadata"]["source_key"] == "rh/policy.md"
    assert document["metadata"]["document_hash"]


class _RecordingStore:
    backend_name = "recording"

    def __init__(self, evidence_on_cross_domain: bool) -> None:
        self.evidence_on_cross_domain = evidence_on_cross_domain
        self.domains = []

    def upsert(self, chunks):
        return UpsertResult(received=len(chunks))

    def search(self, query, domain=None, limit=4):
        del query, limit
        self.domains.append(domain)
        if self.evidence_on_cross_domain and domain is None:
            return [
                RetrievedChunk(
                    "rotation",
                    "The rotation cadence is weekly according to the operations policy.",
                    {
                        "source": "rotation.md",
                        "source_key": "rh/rotation.md",
                        "domain": "rh",
                        "file_type": ".md",
                        "chunk_id": "rotation",
                        "chunk_index": 0,
                    },
                    0.80,
                )
            ]
        return []

    def status(self):
        return {"backend": self.backend_name, "embedding": {"fingerprint": "test"}}


def test_graph_has_three_retrieval_actions_and_widens_only_inferred_domain(
    axiom_settings,
) -> None:
    inferred_store = _RecordingStore(evidence_on_cross_domain=True)
    graph = AxiomAgentGraph(inferred_store, ModelGateway(axiom_settings))

    answer = graph.run("What is the rotation cadence?")

    assert inferred_store.domains == ["engenharia", "engenharia", None]
    assert answer["grounded"] is True
    assert answer["rewrite_count"] == 2
    assert [event["node"] for event in answer["trace"]].count("retrieval") == 3

    explicit_store = _RecordingStore(evidence_on_cross_domain=True)
    explicit = AxiomAgentGraph(explicit_store, ModelGateway(axiom_settings)).run(
        "What is the rotation cadence?", domain="engenharia"
    )
    assert explicit_store.domains == ["engenharia", "engenharia", "engenharia"]
    assert explicit["grounded"] is False


def test_graph_rejects_unknown_explicit_domain(axiom_settings) -> None:
    graph = AxiomAgentGraph(_RecordingStore(False), ModelGateway(axiom_settings))
    with pytest.raises(ValueError, match="Unsupported knowledge domain"):
        graph.run("question", domain="finance")


def test_langsmith_scope_uses_masking_client_without_sensitive_metadata(
    axiom_settings, monkeypatch
) -> None:
    langsmith = pytest.importorskip("langsmith")

    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs

    @contextmanager
    def fake_tracing_context(**kwargs):
        captured["context"] = kwargs
        yield

    monkeypatch.setattr(langsmith, "Client", FakeClient)
    monkeypatch.setattr(langsmith, "tracing_context", fake_tracing_context)
    configured = replace(
        axiom_settings,
        langsmith_tracing=True,
        langsmith_api_key="trace-test-key",
        langsmith_hide_inputs=True,
        langsmith_hide_outputs=True,
    )
    store = _RecordingStore(False)

    AxiomAgentGraph(store, ModelGateway(configured)).run(
        "sensitive employee question", domain="engenharia"
    )

    assert captured["client"]["hide_inputs"]({"secret": "value"}) == {}
    assert captured["client"]["hide_outputs"]({"secret": "value"}) == {}
    assert captured["context"]["project_name"] == configured.langsmith_project
    assert "sensitive employee question" not in repr(captured)
