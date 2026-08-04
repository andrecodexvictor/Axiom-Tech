from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings


@pytest.fixture
def axiom_settings(tmp_path: Path) -> Settings:
    documents = tmp_path / "documents"
    documents.mkdir()
    return Settings(
        documents_dir=documents,
        chroma_path=tmp_path / "chroma",
        chroma_collection="test_axiom_knowledge",
        vector_backend="chroma",
        chunk_size=220,
        chunk_overlap=30,
        cors_origins=("http://testserver",),
        nvidia_enabled=False,
        kimi_api_key="not-used-kimi-key",
        minimax_api_key="not-used-minimax-key",
        deepseek_api_key="not-used-deepseek-key",
        pinecone_api_key="",
        pinecone_index_name="",
        pinecone_environment="",
    )


@pytest.fixture
def sample_documents(axiom_settings: Settings) -> Path:
    hr = axiom_settings.documents_dir / "rh"
    engineering = axiom_settings.documents_dir / "engenharia"
    legal = axiom_settings.documents_dir / "juridico"
    hr.mkdir()
    engineering.mkdir()
    legal.mkdir()
    (hr / "home_office.md").write_text(
        "# Home office benefit\nEmployees receive a monthly home office benefit for approved remote work.\n",
        encoding="utf-8",
    )
    (engineering / "incident.md").write_text(
        "# Incident response\nThe on-call engineer acknowledges a production incident and opens an incident channel.\n",
        encoding="utf-8",
    )
    (legal / "privacy.md").write_text(
        "# LGPD\nPersonal data processing requires a lawful basis and documented purpose.\n",
        encoding="utf-8",
    )
    return axiom_settings.documents_dir
