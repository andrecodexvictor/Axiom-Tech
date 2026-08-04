# Axiom Tech Agent Guide

## Project shape

- `app/` contains the FastAPI boundary, LangGraph workflow, ingestion pipeline, model gateway, and vector-store adapters.
- `frontend/` contains the React/Vite employee console; its API client targets `/api/v1`.
- `documentos/` is the internal corpus used by explicit ingestion.
- `.context/` is the durable dotcontext harness: project docs, agent playbooks, skills, policy, and sensors.
- `docs/` contains the public architecture, API, deployment, ADR, and V3 plan documents.

## Development commands

Backend (Python 3.11+ target):

```powershell
python -m pytest -q
python -m compileall -q app
```

Frontend:

```powershell
npm --prefix frontend install
npm --prefix frontend run check
npm --prefix frontend run build
```

Local runtime:

```powershell
python -m uvicorn app.main:app --reload --port 8000
npm --prefix frontend run dev
```

## Architecture rules

- Keep HTTP concerns in `app/api.py` and `app/schemas.py`; compose the application in `app/main.py`.
- Keep provider integrations behind ports/factories in `app/vectorstore/` and `app/llm_client.py`.
- Corporate answers must be grounded in retrieved citations. Web research is explicit, allowlisted, and fail-closed.
- ChromaDB is the local default; Pinecone remains an optional adapter and must never be claimed as active when unconfigured.
- Do not commit `.env`, credentials, Chroma persistence, dotcontext runtime state, or generated scratch files.

## Validation expectations

Run backend tests, frontend typecheck/build, `git diff --check`, and `docker compose config --quiet` before changing the production contract. Update the relevant ADR or API documentation when a boundary changes.
