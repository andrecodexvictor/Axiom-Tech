# V3 Delivery and Deployment Guide

## Status

The repository contains OCI-oriented container configuration. This guide does **not** claim that an OCI deployment has been created, verified, or exposed publicly.

## Delivery topology

- api image: Python/FastAPI application on port 8000.
- frontend image: static React/Vite build served by Nginx on port 80; Nginx proxies /api/ to the API service in Compose.
- ChromaDB data: a writable persistent volume mounted at /data in the API container.

The images are intentionally separable for OCI Compute, OCI Container Instances, or another OCI-compatible runtime. The frontend can also be hosted separately; in that case set VITE_API_BASE_URL during the frontend build and configure FastAPI CORS with AXIOM_CORS_ORIGINS.

## Local containers

~~~bash
docker compose up --build
~~~

The browser entry point is http://localhost:8080; the API is exposed at http://localhost:8000. The Compose file supplies safe local defaults and reads optional values from the shell or .env; it never copies .env into an image.

To stop containers while retaining the local index:

~~~bash
docker compose down
~~~

To remove the named ChromaDB volume as an intentional reset, use docker compose down -v. This deletes indexed data and should only be done when a re-index is acceptable.

## OCI guidance

1. Build and publish the api and frontend Docker targets to a registry available to the chosen OCI runtime.
2. Configure runtime environment variables or OCI Vault secrets for optional NVIDIA/Pinecone credentials; never bake credentials into an image or source-controlled file.
3. Give the API a persistent writable volume at /data when AXIOM_VECTOR_BACKEND=chroma.
4. Expose the frontend through the selected ingress/load-balancer path and set AXIOM_CORS_ORIGINS if it is cross-origin from the API.
5. Permit outbound egress only when using optional NVIDIA NIM, Pinecone, or the explicit external-research route.

OCI Container Instances may use ephemeral filesystem storage unless a suitable persistent volume is attached. Do not rely on ephemeral storage for the default ChromaDB index; attach persistent storage or explicitly choose the optional Pinecone adapter.

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
