# Axiom Tech Corporate Knowledge Assistant — V3

Axiom Tech V3 is a local-first corporate knowledge assistant for internal policies, engineering and incident guidance, legal/compliance material, and repository/API references.

> **Delivery status:** the repository contains the V3 architecture, contracts, and OCI-oriented delivery assets. This is not a claim that an OCI or production deployment, a public demo, or screenshots exist.

## What V3 changes

- A Python modular monolith with FastAPI as the public API boundary.
- A real LangGraph StateGraph for routing, retrieval, specialist handling, evidence grading, up to two rewrites, grounded synthesis, and fallback.
- Persistent ChromaDB as the local default; Pinecone is an explicitly configured optional adapter.
- Deterministic local behavior without NVIDIA or Pinecone credentials; NVIDIA NIM is optional.
- A React/Vite client that calls the versioned API and renders answer/source/trace data.
- Structured citations that preserve source, domain, file type, chunk, safe corpus-relative path or URL, and available page/slide/sheet metadata.
- Explicit allowlisted technical web research that is disabled by default and never acts as a hidden fallback.

The legacy specification is retained at `docs/legacy/v1-architecture.md`. V3 authority lives in `.context`, `.stack`, `dotarchitecture-input.yaml`, `dotarchitecture.yaml`, `docs/architecture.md`, and the V3 ADRs. Legacy Streamlit/CLI or simulated UI material should not be treated as the V3 contract during migration.

## Architecture

~~~text
React/Vite client
       |
       v
FastAPI /api/v1
       |
       v
Application use cases -> LangGraph StateGraph
       |                    |
       v                    v
Ingestion              Retrieval / model ports
       |                    |
Internal corpus      ChromaDB default
                     Pinecone/NVIDIA NIM optional
~~~

Corporate answers are evidence-backed or explicitly limited. External research is an explicit route; it is not a hidden fallback for missing internal evidence.

To enable the explicit `web` domain, set `AXIOM_WEB_ENABLED=true`, provide `SERPER_API_KEY`, and configure `AXIOM_WEB_ALLOWLIST` with trusted technical documentation hosts. Candidate and redirect URLs remain HTTPS-only and must match that allowlist.

Read the detailed architecture in docs/architecture.md, the HTTP contract in docs/api.md, and product/interface intent in PRODUCT.md and DESIGN.md.

## Local development

### 1. Configure safe local defaults

~~~bash
copy .env.example .env
~~~

On macOS/Linux, use cp instead of copy. The default configuration needs no cloud credentials and persists ChromaDB data under ./.axiom_chroma.

### 2. Start the API

~~~bash
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
~~~

API endpoints:

- GET /api/v1/health
- GET /api/v1/status
- POST /api/v1/query
- POST /api/v1/ingest

### 3. Start the React/Vite client

~~~bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev
~~~

If pnpm is not installed, `npm --prefix frontend install` and `npm --prefix frontend run dev` provide the equivalent local workflow.

Vite development proxies API traffic to the FastAPI server. Set VITE_API_BASE_URL only when the frontend is intentionally deployed on a different origin.

## Containers and OCI handoff

~~~bash
docker compose up --build
~~~

This starts the browser entry point at http://localhost:8080 and the API at http://localhost:8000, with a named ChromaDB volume. The frontend image proxies /api/ to the API service. See docs/deployment.md for persistence, OCI, runtime-secret, and reset guidance.

## Grounding contract

Each query response contains an answer, selected domain/specialist, citations, grounding status, rewrite count, and a safe graph-trace event list. A citation records the origin file and available metadata; the response must not fabricate citations. If the corpus cannot substantiate a corporate claim, the API returns a direct limitation rather than an invented policy.

## Repository guide

~~~text
app/                    Python FastAPI, graph, ingestion, and adapter modules
frontend/               React/Vite client
documentos/             Internal corpus fixtures
docs/                   V3 architecture, API, delivery docs, and ADRs
Dockerfile              API and frontend OCI-compatible image targets
docker-compose.yml      Local API/frontend/persistent-ChromaDB topology
.env.example            Safe runtime configuration template
~~~

## Validation commands

~~~bash
python -m compileall -q app
pnpm --dir frontend build
docker compose config --quiet
~~~

These are local checks, not a declaration that they have been run in a cloud environment.
