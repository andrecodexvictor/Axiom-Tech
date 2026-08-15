"""FastAPI entry point and backwards-compatible command-line interface."""

from __future__ import annotations

import argparse
import logging
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, status as http_status
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import Settings, settings
from app.schemas import (
    DocumentUploadResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    SourcePreviewResponse,
    SourcesResponse,
    StatusResponse,
)
from app.ingestion.upload import UploadRejectedError, UploadTooLargeError
from app.service import KnowledgeService, create_knowledge_service


logger = logging.getLogger(__name__)


def create_app(
    service: Optional[KnowledgeService] = None, configuration: Settings = settings
) -> FastAPI:
    """Build an API instance; injected services make integration tests isolated."""

    application = FastAPI(title="Axiom Tech Knowledge API", version=__version__)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(configuration.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    application.state.knowledge_service = service or create_knowledge_service(configuration)

    @application.get("/api/v1/health", response_model=HealthResponse)
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @application.get("/api/v1/status", response_model=StatusResponse)
    def status() -> dict:
        return application.state.knowledge_service.status()

    @application.post(
        "/api/v1/ingest", response_model=IngestResponse, response_model_exclude_none=True
    )
    def ingest(request: IngestRequest) -> dict:
        try:
            return application.state.knowledge_service.ingest(request.path, force=request.force).as_dict()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Ingestion target was not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="Ingestion target is outside the configured documents directory") from exc
        except Exception as exc:
            logger.error("Ingestion failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Ingestion is temporarily unavailable") from exc

    @application.post(
        "/api/v1/documents",
        response_model=DocumentUploadResponse,
        status_code=http_status.HTTP_201_CREATED,
    )
    def upload_document(
        file: UploadFile = File(...),
        domain: str = Form(..., min_length=2, max_length=32),
    ) -> dict:
        try:
            return application.state.knowledge_service.upload_document(
                file.file,
                filename=file.filename or "",
                domain=domain,
            ).as_dict()
        except UploadTooLargeError as exc:
            raise HTTPException(status_code=413, detail="Document exceeds the 15 MB limit") from exc
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail="A document with this name already exists") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="Document destination is not allowed") from exc
        except UploadRejectedError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Document upload failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Document upload is temporarily unavailable") from exc

    @application.post("/api/v1/query", response_model=QueryResponse, response_model_exclude_none=True)
    def query(request: QueryRequest) -> dict:
        try:
            return application.state.knowledge_service.query(
                request.question,
                domain=request.domain,
                top_k=request.top_k,
                response_mode=request.response_mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Question is invalid") from exc
        except Exception as exc:
            logger.error("Query failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Query service is temporarily unavailable") from exc

    @application.get("/api/v1/sources", response_model=SourcesResponse)
    def sources() -> dict:
        try:
            return application.state.knowledge_service.sources()
        except Exception as exc:
            logger.error("Source inventory failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Source inventory is temporarily unavailable") from exc

    @application.get("/api/v1/sources/preview", response_model=SourcePreviewResponse)
    def source_preview(path: str = Query(..., min_length=1, max_length=4096)) -> dict:
        try:
            return application.state.knowledge_service.source_preview(path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Source document was not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="Source document is outside the configured corpus") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Source document cannot be previewed") from exc
        except Exception as exc:
            logger.error("Source preview failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Source preview is temporarily unavailable") from exc

    @application.post(
        "/api/v1/embeddings/rebuild",
        response_model=IngestResponse,
        response_model_exclude_none=True,
    )
    def rebuild_embeddings() -> dict:
        try:
            return application.state.knowledge_service.rebuild_embeddings().as_dict()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Embedding source directory was not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="Embedding source is outside the configured documents directory") from exc
        except Exception as exc:
            logger.error("Embedding rebuild failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Embedding rebuild is temporarily unavailable") from exc

    return application


app = create_app()


def initialize_knowledge_base(path: Optional[str] = None) -> dict:
    """Legacy CLI helper retained for existing scripts."""

    report = app.state.knowledge_service.ingest(path)
    result = report.as_dict()
    print(
        "[Ingestion] received={received} inserted={inserted} updated={updated} unchanged={unchanged} skipped={skipped}".format(
            **result
        )
    )
    return result


def run_cli() -> None:
    print("Axiom Tech Knowledge Assistant V3")
    initialize_knowledge_base()
    print("Ready. Type a question, or 'exit' to quit.")
    while True:
        try:
            question = input("\n[Employee Question]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return
        if not question or question.lower() in {"exit", "quit"}:
            print("Goodbye!")
            return
        try:
            result = app.state.knowledge_service.query(question)
            print("\n[{0} | {1}]\n{2}".format(result["domain"], result["specialist"], result["answer"]))
            if result["citations"]:
                print("\nSources:")
                for citation in result["citations"]:
                    print("- {0}".format(citation["source"]))
        except Exception as exc:
            print("[Error] {0}".format(type(exc).__name__))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Axiom Tech Knowledge Assistant V3")
    parser.add_argument("--cli", action="store_true", help="Run the interactive CLI")
    parser.add_argument("--ingest", action="store_true", help="Ingest documents and exit")
    args = parser.parse_args()
    if args.ingest:
        initialize_knowledge_base()
    else:
        run_cli()
