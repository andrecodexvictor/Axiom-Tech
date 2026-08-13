"""Application service shared by FastAPI and the backwards-compatible CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import Settings, settings
from app.graph import AxiomAgentGraph
from app.ingestion.chunker import DocumentChunker
from app.ingestion.loader import DocumentLoader
from app.llm_client import ModelGateway
from app.vectorstore.factory import create_vector_store
from app.vectorstore.port import UpsertResult, VectorStorePort


@dataclass
class IngestFileResult:
    source: str
    status: str
    chunks: int
    message: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        value: Dict[str, Any] = {"source": self.source, "status": self.status, "chunks": self.chunks}
        if self.message:
            value["message"] = self.message
        return value


@dataclass
class IngestReport:
    received: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    files: List[IngestFileResult] = field(default_factory=list)

    def add(self, result: UpsertResult) -> None:
        self.received += result.received
        self.inserted += result.inserted
        self.updated += result.updated + result.removed
        self.unchanged += result.unchanged

    def as_dict(self) -> Dict[str, Any]:
        return {
            "received": self.received,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "files": [item.as_dict() for item in self.files],
        }


class KnowledgeService:
    """Use-case boundary: file ingestion and grounded queries."""

    def __init__(
        self,
        configuration: Settings,
        vector_store: VectorStorePort,
        model_gateway: ModelGateway,
    ) -> None:
        self.configuration = configuration
        self.vector_store = vector_store
        self.model_gateway = model_gateway
        self.chunker = DocumentChunker(configuration.chunk_size, configuration.chunk_overlap)
        self.graph = AxiomAgentGraph(vector_store, model_gateway)

    def ingest(self, path: Optional[str] = None) -> IngestReport:
        target = self._resolve_ingest_target(path)
        report = IngestReport()
        for file_path in DocumentLoader.iter_supported_files(target):
            try:
                documents = DocumentLoader.load_file(
                    file_path, source_root=self.configuration.documents_dir
                )
                chunks = self.chunker.split_documents(documents)
                if not chunks:
                    report.skipped += 1
                    report.files.append(IngestFileResult(file_path.name, "skipped", 0, "No extractable text"))
                    continue
                outcome = self.vector_store.upsert(chunks)
                report.add(outcome)
                if outcome.inserted or outcome.updated or outcome.removed:
                    state = "indexed"
                else:
                    state = "unchanged"
                report.files.append(IngestFileResult(file_path.name, state, len(chunks)))
            except Exception as exc:
                # File diagnostics must not reveal document text, credentials, or
                # provider response bodies.  A class name is actionable enough.
                report.skipped += 1
                report.files.append(IngestFileResult(file_path.name, "skipped", 0, type(exc).__name__))
        return report

    def query(self, question: str, domain: Optional[str] = None, top_k: int = 4) -> Dict[str, Any]:
        state = self.graph.run(question, domain=domain, top_k=top_k)
        return {
            "answer": state["final_answer"],
            "domain": state.get("domain", state.get("classified_domain", "engenharia")),
            "specialist": state.get("specialist", state.get("next_agent", "engineering_operations")),
            "citations": [self._public_citation(citation) for citation in state.get("citations", [])],
            "trace": state.get("trace", []),
            "rewrite_count": int(state.get("rewrite_count", 0)),
            "grounded": bool(state.get("grounded", False)),
        }

    def status(self) -> Dict[str, Any]:
        store = self.vector_store.status()
        embedding = dict(store.get("embedding", {}) or {})
        retrieval = dict(store.get("retrieval", {}) or {})
        return {
            "status": "ok" if store.get("backend") == "chroma" else "degraded",
            "version": "3.0.0",
            "vector_store": {
                "backend": store.get("backend", "unknown"),
                "collection": store.get("collection", ""),
                "physical_collection": store.get("physical_collection") or None,
                "document_count": int(store.get("document_count", 0)),
                "embedding": {
                    "provider": str(embedding.get("provider", "unavailable")),
                    "model": str(embedding.get("model", "")) or None,
                    "dimensions": int(embedding.get("dimensions", 0)),
                    "fingerprint": str(embedding.get("fingerprint", "")),
                    "mode": str(embedding.get("mode", "disabled")),
                    "configured": bool(embedding.get("configured", False)),
                },
                "retrieval": {
                    "strategy": str(retrieval.get("strategy", "unavailable")),
                    "candidate_multiplier": int(retrieval.get("candidate_multiplier", 0)),
                    "min_score": float(retrieval.get("min_score", 0.0)),
                    "lexical_weight": float(retrieval.get("lexical_weight", 0.0)),
                    "mmr_lambda": float(retrieval.get("mmr_lambda", 0.0)),
                },
            },
            "models": self.model_gateway.status(),
            # Status reports a logical label, never an absolute host path.
            "documents_dir": self.configuration.documents_dir.name or "configured",
            "web_research": {
                "enabled": self.configuration.web_enabled,
                "configured": self.configuration.web_search_configured,
                "allowlist_hosts": len(self.configuration.web_allowlist),
            },
            "observability": {
                "provider": "langsmith",
                "enabled": self.configuration.langsmith_enabled,
                "configured": self.configuration.langsmith_configured,
                "project": self.configuration.langsmith_project,
                "inputs_hidden": self.configuration.langsmith_hide_inputs,
                "outputs_hidden": self.configuration.langsmith_hide_outputs,
            },
        }

    def _resolve_ingest_target(self, requested: Optional[str]) -> Path:
        base = self.configuration.documents_dir.resolve()
        target = Path(requested).expanduser().resolve() if requested else base
        try:
            target.relative_to(base)
        except ValueError as exc:
            raise PermissionError("The ingestion path must be inside AXIOM_DOCUMENTS_DIR") from exc
        if not target.exists():
            raise FileNotFoundError("Ingestion path does not exist")
        return target

    def _public_citation(self, citation: Dict[str, Any]) -> Dict[str, Any]:
        """Strip absolute server paths from API citations.

        Documents under the configured corpus retain a useful stable relative path
        (for example ``rh/home_office.md``); anything outside that corpus has no
        path field at all. URL citations from web research are preserved.
        """

        public = dict(citation)
        raw_path = public.get("path")
        if not raw_path:
            public.pop("path", None)
            return public
        try:
            relative = Path(str(raw_path)).resolve().relative_to(self.configuration.documents_dir.resolve())
        except (OSError, ValueError):
            public.pop("path", None)
        else:
            public["path"] = relative.as_posix()
        return public


def create_knowledge_service(configuration: Settings = settings) -> KnowledgeService:
    store = create_vector_store(configuration)
    gateway = ModelGateway(configuration)
    return KnowledgeService(configuration, store, gateway)
