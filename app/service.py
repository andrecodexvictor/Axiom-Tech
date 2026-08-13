"""Application service shared by FastAPI and the backwards-compatible CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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

    def ingest(self, path: Optional[str] = None, *, force: bool = False) -> IngestReport:
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
                outcome = (
                    self.vector_store.upsert(chunks, force=True)
                    if force
                    else self.vector_store.upsert(chunks)
                )
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

    def rebuild_embeddings(self) -> IngestReport:
        """Re-embed every supported corpus chunk using the active provider."""

        return self.ingest(force=True)

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
            "duration_ms": float(state.get("duration_ms", 0.0)),
            "timings_ms": {
                str(key): round(float(value), 1)
                for key, value in dict(state.get("timings_ms", {}) or {}).items()
            },
        }

    def status(self) -> Dict[str, Any]:
        store = self.vector_store.status()
        embedding = dict(store.get("embedding", {}) or {})
        retrieval = dict(store.get("retrieval", {}) or {})
        document_count = int(store.get("document_count", 0))
        backend = str(store.get("backend", "unknown"))
        ready = backend == "chroma" and document_count > 0
        public_reason = str(store.get("reason", "")).strip()
        if public_reason not in {
            "",
            "chroma_unavailable",
            "embedding_not_configured",
            "unsupported_vector_backend",
            "pinecone_not_configured",
        }:
            public_reason = "vector_store_unavailable"
        return {
            "status": "ok" if ready else ("empty" if backend == "chroma" else "degraded"),
            "version": "3.0.0",
            "vector_store": {
                "backend": backend,
                "collection": store.get("collection", ""),
                "physical_collection": store.get("physical_collection") or None,
                "document_count": document_count,
                "source_count": (
                    int(store["source_count"])
                    if store.get("source_count") is not None
                    else None
                ),
                "ready": ready,
                "reason": public_reason or None,
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

    def sources(self) -> Dict[str, Any]:
        """Return a safe inventory of corpus files and their index state."""

        base = self.configuration.documents_dir.resolve()
        indexed_items = getattr(self.vector_store, "source_inventory", lambda: [])()
        indexed_by_key = {
            str(item.get("source_key", "")): item
            for item in indexed_items
            if item.get("source_key")
        }
        records: List[Dict[str, Any]] = []
        for file_path in DocumentLoader.iter_supported_files(base):
            relative_path = file_path.resolve().relative_to(base).as_posix()
            indexed = indexed_by_key.get(relative_path, {})
            indexed_chunks = int(indexed.get("chunks", 0))
            stat = file_path.stat()
            indexed_size = self._optional_int(indexed.get("size_bytes"))
            indexed_modified_ns = self._optional_int(indexed.get("modified_ns"))
            expected_chunks = indexed_chunks

            if indexed_chunks == 0:
                state = "pending"
                message = "Ainda não indexado"
            elif indexed_size is None or indexed_modified_ns is None:
                # Older collections do not carry the cheap filesystem stamp.
                # Do not turn a status call into a full document parse; an
                # explicit rebuild upgrades those records and enables exact
                # change detection from the next request onward.
                state = "indexed"
                message = "Índice existente; gere embeddings novamente para habilitar a detecção de alterações"
            elif indexed_size != int(stat.st_size) or indexed_modified_ns != int(stat.st_mtime_ns):
                state = "stale"
                message = "O arquivo mudou desde a última indexação"
            else:
                state = "indexed"
                message = None

            item: Dict[str, Any] = {
                "path": relative_path,
                "domain": file_path.parent.name,
                "file_type": file_path.suffix.lower().lstrip("."),
                "size_bytes": int(stat.st_size),
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                "indexed_chunks": indexed_chunks,
                "expected_chunks": expected_chunks,
                "status": state,
            }
            if message:
                item["message"] = message
            records.append(item)

        return {
            "total": len(records),
            "indexed": sum(item["status"] == "indexed" for item in records),
            "pending": sum(item["status"] != "indexed" for item in records),
            "sources": records,
        }

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

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
