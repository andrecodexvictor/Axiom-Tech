from __future__ import annotations

from dataclasses import replace
import zipfile
from pathlib import Path

import pytest
import httpx

from app.agents.web_research import WebResearchAgent
from app.graph import LANGGRAPH_AVAILABLE
from app.ingestion.loader import DocumentLoader
from app.service import create_knowledge_service


def test_pptx_loader_extracts_slide_text_without_cloud_credentials(tmp_path: Path) -> None:
    """The XML fallback makes PPTX extraction testable without a model/API key."""

    deck_dir = tmp_path / "estrategico"
    deck_dir.mkdir()
    deck = deck_dir / "roadmap.pptx"
    slide_xml = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
           xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Roadmap 2026</a:t></a:r></a:p>
      <a:p><a:r><a:t>Reliability milestone</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>
    </p:sld>'''
    with zipfile.ZipFile(deck, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", slide_xml)

    documents = DocumentLoader.load_file(deck)

    assert len(documents) == 1
    assert documents[0]["metadata"]["slide"] == 1
    assert "Roadmap 2026" in documents[0]["content"]
    assert "Reliability milestone" in documents[0]["content"]


def test_ingestion_is_idempotent_and_query_is_grounded(axiom_settings, sample_documents) -> None:
    service = create_knowledge_service(axiom_settings)

    first = service.ingest()
    count_after_first = service.status()["vector_store"]["document_count"]
    second = service.ingest()
    count_after_second = service.status()["vector_store"]["document_count"]

    assert first.inserted > 0
    assert second.inserted == 0
    assert second.unchanged == first.received
    assert count_after_first == count_after_second

    answer = service.query("What is the home office benefit?", domain="rh")

    assert answer["grounded"] is True
    assert answer["domain"] == "rh"
    assert answer["citations"]
    assert answer["citations"][0]["source"] == "home_office.md"
    assert answer["citations"][0]["path"] == "rh/home_office.md"
    assert str(axiom_settings.documents_dir) not in answer["citations"][0]["path"]
    assert "monthly home office benefit" in answer["answer"].lower()
    assert [event["node"] for event in answer["trace"]] == [
        "supervisor",
        "retrieval",
        "specialist",
        "grade",
        "synthesize",
    ]


def test_embedding_fingerprint_change_selects_empty_collection_until_reingested(
    axiom_settings, sample_documents
) -> None:
    pytest.importorskip("chromadb")
    original = create_knowledge_service(axiom_settings)
    original.ingest()
    original_status = original.vector_store.status()

    upgraded_settings = replace(axiom_settings, embedding_dimensions=512)
    upgraded = create_knowledge_service(upgraded_settings)
    upgraded_status = upgraded.vector_store.status()

    assert original_status["physical_collection"] != upgraded_status["physical_collection"]
    assert original_status["document_count"] > 0
    assert upgraded_status["document_count"] == 0
    assert upgraded.ingest().inserted > 0
    assert upgraded.query("What is the home office benefit?", domain="rh")["grounded"] is True


def test_unsupported_question_rewrites_at_most_twice_then_falls_back(axiom_settings, sample_documents) -> None:
    service = create_knowledge_service(axiom_settings)
    service.ingest()

    answer = service.query("Explain zyxwplugh quantum banana protocol", domain="engenharia")

    assert answer["grounded"] is False
    assert answer["citations"] == []
    assert answer["rewrite_count"] == 2
    assert [event["node"] for event in answer["trace"]].count("rewrite") == 2
    assert answer["trace"][-1]["node"] == "fallback"


def test_runtime_uses_actual_langgraph_when_dependency_is_installed(axiom_settings) -> None:
    pytest.importorskip("langgraph")
    service = create_knowledge_service(axiom_settings)

    assert LANGGRAPH_AVAILABLE is True
    assert service.graph.graph.__class__.__module__.startswith("langgraph")


def test_web_domain_is_explicit_and_disabled_without_fabricated_citations(axiom_settings) -> None:
    service = create_knowledge_service(axiom_settings)

    answer = service.query("Search the web for the latest secure deployment guidance", domain="web")

    assert answer["domain"] == "web"
    assert answer["specialist"] == "web_research"
    assert answer["grounded"] is False
    assert answer["citations"] == []
    assert "disabled" in answer["answer"].lower()
    nodes = [event["node"] for event in answer["trace"]]
    assert nodes[0] == "supervisor"
    assert set(nodes[1:]) == {"web_research"}
    assert "retrieval" not in nodes
    assert "grade" not in nodes


def test_local_answers_follow_the_question_language(axiom_settings, sample_documents) -> None:
    service = create_knowledge_service(axiom_settings)
    service.ingest()

    grounded = service.query("Qual é o benefício de home office?", domain="rh")
    unsupported = service.query("Qual é o protocolo zyxwplugh?", domain="engenharia")
    external = service.query("Pesquise na web a versão mais recente", domain="web")

    assert "resposta fundamentada em português" in grounded["answer"]
    assert "monthly home office benefit" not in grounded["answer"].lower()
    assert unsupported["answer"].startswith("Não consigo fundamentar")
    assert "desativada" in external["answer"].lower()


def test_portuguese_lgpd_question_retrieves_english_policy(axiom_settings, sample_documents) -> None:
    service = create_knowledge_service(axiom_settings)
    service.ingest()

    answer = service.query(
        "Quais são os direitos dos titulares segundo a política de LGPD?",
        domain="juridico",
        top_k=6,
    )

    assert answer["grounded"] is True
    assert answer["citations"]
    assert answer["citations"][0]["source"] == "privacy.md"


def test_web_url_validation_enforces_https_allowlist_and_ssrf_guards(axiom_settings) -> None:
    configured = replace(
        axiom_settings,
        web_enabled=True,
        serper_api_key="not-used-serper-key",
        web_allowlist=("example.com",),
    )
    agent = WebResearchAgent(configured)

    assert agent.is_allowed_url("https://example.com/guidance")
    assert agent.is_allowed_url("https://docs.example.com/guidance?version=3")
    assert not agent.is_allowed_url("http://example.com/guidance")
    assert not agent.is_allowed_url("https://example.com.evil.invalid/guidance")
    assert not agent.is_allowed_url("https://example.com@evil.invalid/guidance")
    assert not agent.is_allowed_url("https://127.0.0.1/admin")
    assert not agent.is_allowed_url("https://[::1]/admin")
    assert not agent.is_allowed_url("https://example.com:444/guidance")


def test_enabled_web_research_fetches_only_allowlisted_evidence_and_returns_url_citation(axiom_settings) -> None:
    configured = replace(
        axiom_settings,
        web_enabled=True,
        serper_api_key="test-serper-key",
        web_allowlist=("example.com",),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and str(request.url) == "https://google.serper.dev/search":
            return httpx.Response(
                200,
                json={
                    "organic": [
                        {"title": "Reliability guide", "link": "https://docs.example.com/reliability"},
                        {"title": "Rejected", "link": "https://evil.invalid/not-allowed"},
                    ]
                },
                request=request,
            )
        if request.method == "GET" and str(request.url) == "https://docs.example.com/reliability":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=(
                    b"<html><head><title>Reliability guide</title></head><body>"
                    b"The reliability guide recommends testing recovery procedures every quarter."
                    b"</body></html>"
                ),
                request=request,
            )
        raise AssertionError("Unexpected outbound request: {0} {1}".format(request.method, request.url))

    agent = WebResearchAgent(
        configured,
        client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        resolver=lambda _host: ("93.184.216.34",),
    )
    result = agent.research("What does the reliability guide recommend?", limit=4)

    assert result.grounded is True
    assert result.citations[0]["url"] == "https://docs.example.com/reliability"
    assert result.citations[0].get("path") is None
    assert "testing recovery procedures" in result.answer.lower()
    assert [event["event"].split(".", 1)[0] for event in result.trace] == [
        "plan",
        "search",
        "fetch",
        "evaluate",
        "refine_synthesize",
    ]


def test_web_research_rejects_allowlisted_host_resolving_to_private_ip(axiom_settings) -> None:
    configured = replace(
        axiom_settings,
        web_enabled=True,
        serper_api_key="test-serper-key",
        web_allowlist=("example.com",),
    )
    fetched = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "organic": [
                        {"title": "Private target", "link": "https://docs.example.com/internal"}
                    ]
                },
                request=request,
            )
        fetched.append(str(request.url))
        raise AssertionError("A private resolution must be rejected before HTTP GET")

    agent = WebResearchAgent(
        configured,
        client_factory=lambda: httpx.Client(
            transport=httpx.MockTransport(handler), follow_redirects=False
        ),
        resolver=lambda _host: ("127.0.0.1",),
    )

    result = agent.research("What does the internal guide require?")

    assert result.grounded is False
    assert result.citations == []
    assert fetched == []
