from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.service import create_knowledge_service


def test_versioned_api_returns_grounded_contract_and_never_echoes_credentials(
    axiom_settings, sample_documents
) -> None:
    service = create_knowledge_service(axiom_settings)
    application = create_app(service=service, configuration=axiom_settings)

    with TestClient(application) as client:
        health = client.get("/api/v1/health")
        status_before = client.get("/api/v1/status")
        ingest = client.post("/api/v1/ingest", json={})
        query = client.post(
            "/api/v1/query", json={"question": "What is the home office benefit?", "domain": "rh"}
        )

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": "3.0.0"}
    assert status_before.status_code == 200
    assert ingest.status_code == 200
    assert ingest.json()["inserted"] > 0
    assert query.status_code == 200
    body = query.json()
    assert set(body) == {"answer", "domain", "specialist", "citations", "trace", "rewrite_count", "grounded"}
    assert body["grounded"] is True
    assert body["citations"][0]["source"] == "home_office.md"
    serialized = json.dumps({"status": status_before.json(), "query": body})
    assert "not-used-kimi-key" not in serialized
    assert "not-used-minimax-key" not in serialized
    assert "not-used-deepseek-key" not in serialized


def test_ingest_rejects_a_path_outside_configured_documents_root(axiom_settings) -> None:
    application = create_app(service=create_knowledge_service(axiom_settings), configuration=axiom_settings)
    with TestClient(application) as client:
        response = client.post("/api/v1/ingest", json={"path": str(axiom_settings.documents_dir.parent)})

    assert response.status_code == 403


def test_query_api_accepts_explicit_web_domain_without_outbound_access_when_disabled(axiom_settings) -> None:
    application = create_app(service=create_knowledge_service(axiom_settings), configuration=axiom_settings)
    with TestClient(application) as client:
        response = client.post("/api/v1/query", json={"question": "Search the web for a release note", "domain": "web"})

    assert response.status_code == 200
    body = response.json()
    assert body["domain"] == "web"
    assert body["grounded"] is False
    assert body["citations"] == []
