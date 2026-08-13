# V3 Delivery and Deployment Guide

## Status

The repository contains OCI-oriented container configuration. This guide does **not** claim that an OCI deployment has been created, verified, or exposed publicly.

## Delivery topology

- api image: Python/FastAPI application on port 8000.
- frontend image: static React/Vite build served by Nginx on port 80; Nginx proxies /api/ to the API service in Compose.
- ChromaDB data: a writable persistent volume mounted at /data in the API container.

The images are intentionally separable for OCI Compute, OCI Container Instances, or another OCI-compatible runtime. The frontend can also be hosted separately; in that case set VITE_API_BASE_URL during the frontend build and configure FastAPI CORS with AXIOM_CORS_ORIGINS.

For the challenge’s first live proof, use [docs/oci-mcp-deployment.md](oci-mcp-deployment.md). It selects OCI Compute plus a durable Block Volume and OCI Vault because the default ChromaDB index must survive a container restart. The runbook also defines the Oracle OCI Cloud MCP read-before-write workflow.

## Immutable image delivery

Production images are built only by `.github/workflows/ci.yml`. Successful
pushes to `main` publish the API and frontend targets to GHCR for both AMD64 and
ARM64, tagged with the complete source commit (`sha-<commit>`). The VM never
compiles Python or Node dependencies.

`docker-compose.yml` requires `AXIOM_API_IMAGE` and `AXIOM_FRONTEND_IMAGE` to
reference those immutable images. The deployment workflow performs registry
login, `docker compose pull`, and `docker compose up --no-build`; credentials
are not copied into either image.

For local application development, run Uvicorn and Vite directly as documented
in the README. Docker image builds remain a CI responsibility.

To stop containers while retaining the local index:

~~~bash
docker compose down
~~~

To remove the named ChromaDB volume as an intentional reset, use docker compose down -v. This deletes indexed data and should only be done when a re-index is acceptable.

## OCI guidance

1. Let GitHub Actions build and publish the API and frontend Docker targets to GHCR; do not build on the OCI VM.
2. Configure runtime environment variables or OCI Vault secrets for optional NVIDIA/Pinecone credentials; never bake credentials into an image or source-controlled file.
3. Give the API a persistent writable volume at /data when AXIOM_VECTOR_BACKEND=chroma.
4. Expose the frontend through the selected ingress/load-balancer path and set AXIOM_CORS_ORIGINS if it is cross-origin from the API.
5. Permit outbound egress only when using optional NVIDIA NIM, Pinecone, or the explicit external-research route.

6. If LangSmith is approved, set `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, and the correct `LANGSMITH_ENDPOINT` as runtime secrets. Keep `LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true` until the data-retention review allows trace payloads.

OCI Container Instances may use ephemeral filesystem storage unless a suitable persistent volume is attached. Do not rely on ephemeral storage for the default ChromaDB index; attach persistent storage or explicitly choose the optional Pinecone adapter.

The current delivery decision is recorded in [ADR 006](adr/006-oci-go-live-and-observability.md). It is a deployment target and runbook, not a claim that OCI resources already exist.

## Runtime configuration

Copy .env.example to .env for local overrides. Key settings are:

| Setting | Purpose | Safe default |
| --- | --- | --- |
| AXIOM_VECTOR_BACKEND | Chooses the vector adapter | chroma |
| AXIOM_CHROMA_PATH | Persistent ChromaDB directory | ./.axiom_chroma locally, /data/chroma in containers |
| AXIOM_CHROMA_COLLECTION | Collection name | axiom_knowledge |
| AXIOM_NVIDIA_ENABLED | Enables optional NVIDIA NIM calls | false |
| AXIOM_CORS_ORIGINS | Comma-separated allowed browser origins | local Vite/Compose origins |
| PINECONE_* | Reserved for a deployment-specific Pinecone adapter | unset; selecting Pinecone otherwise fails transparently |

## Operational checks

- GET /api/v1/health is the liveness/readiness entry point for local and container checks.
- GET /api/v1/status reports safe runtime mode/status data; it must not reveal credentials.
- Ingestion is explicit through POST /api/v1/ingest; it is not run invisibly by a browser request.
- Retain logs and graph-trace summaries without storing question content or secret values beyond the agreed operational policy.
