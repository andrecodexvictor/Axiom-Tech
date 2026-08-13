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
    assert status_before.json()["models"] == {
        "gateway": "deterministic",
        "remote_enabled": False,
        "model": None,
        "fallback": "none",
        "routes": [
            {
                "name": "deterministic",
                "provider": "deterministic",
                "model": None,
                "configured": True,
                "circuit_state": "closed",
            }
        ],
    }
    assert status_before.json()["documents_dir"] == "documents"
    assert status_before.json()["observability"] == {
        "provider": "langsmith",
        "enabled": False,
        "configured": False,
        "project": "axiom-tech-v3",
        "inputs_hidden": True,
        "outputs_hidden": True,
    }
    assert ingest.status_code == 200
    assert ingest.json()["inserted"] > 0
    assert query.status_code == 200
    body = query.json()
    assert {
        "answer",
        "domain",
        "specialist",
        "citations",
        "trace",
        "rewrite_count",
        "grounded",
        "duration_ms",
        "timings_ms",
    } <= set(body)
    assert body["grounded"] is True
    assert body["citations"][0]["source"] == "home_office.md"
    assert body["duration_ms"] >= 0
    assert body["timings_ms"]["total_ms"] >= 0
    serialized = json.dumps({"status": status_before.json(), "query": body})
    assert "not-used-kimi-key" not in serialized
    assert "not-used-minimax-key" not in serialized
    assert "not-used-deepseek-key" not in serialized
    assert str(axiom_settings.documents_dir.parent) not in serialized


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


def test_source_inventory_and_embedding_rebuild_are_explicit(axiom_settings, sample_documents) -> None:
    service = create_knowledge_service(axiom_settings)
    application = create_app(service=service, configuration=axiom_settings)

    with TestClient(application) as client:
        before = client.get("/api/v1/sources")
        ingest = client.post("/api/v1/ingest", json={})
        after = client.get("/api/v1/sources")
        rebuild = client.post("/api/v1/embeddings/rebuild")

    assert before.status_code == 200
    assert before.json()["total"] == 3
    assert before.json()["indexed"] == 0
    assert ingest.status_code == 200
    assert after.json()["indexed"] == 3
    assert all(item["status"] == "indexed" for item in after.json()["sources"])
    assert rebuild.status_code == 200
    assert rebuild.json()["updated"] > 0


def test_source_inventory_marks_changed_files_without_reparsing_them(
    axiom_settings, sample_documents
) -> None:
    service = create_knowledge_service(axiom_settings)
    service.ingest()
    target = axiom_settings.documents_dir / "rh" / "home_office.md"
    target.write_text(target.read_text(encoding="utf-8") + "\nUpdated allowance note.\n", encoding="utf-8")

    inventory = service.sources()

    changed = next(item for item in inventory["sources"] if item["path"] == "rh/home_office.md")
    assert changed["status"] == "stale"
    assert changed["indexed_chunks"] > 0
