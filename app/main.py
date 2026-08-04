"""FastAPI entry point and backwards-compatible command-line interface."""

from __future__ import annotations

import argparse
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import Settings, settings
from app.schemas import (
    HealthResponse,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    StatusResponse,
)
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
            return application.state.knowledge_service.ingest(request.path).as_dict()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Ingestion target was not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="Ingestion target is outside the configured documents directory") from exc
        except Exception as exc:
            logger.error("Ingestion failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Ingestion is temporarily unavailable") from exc

    @application.post("/api/v1/query", response_model=QueryResponse, response_model_exclude_none=True)
    def query(request: QueryRequest) -> dict:
        try:
            return application.state.knowledge_service.query(
                request.question, domain=request.domain, top_k=request.top_k
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Question is invalid") from exc
        except Exception as exc:
            logger.error("Query failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Query service is temporarily unavailable") from exc

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
