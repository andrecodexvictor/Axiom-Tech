# V3 Architecture

## Status

This document records the V3 architecture target and delivery constraints. It does not assert a live OCI deployment or production service.

## Shape

V3 is a **Python modular monolith**. FastAPI is the public boundary; graph orchestration, retrieval, ingestion, model access, and storage adapters remain separately testable modules within one deployable backend. The React/Vite client is a separate static web build that talks to the versioned API.

~~~mermaid
flowchart LR
    UI[React / Vite client] --> API[FastAPI /api/v1]
    API --> APP[Application service]
    APP --> GRAPH[LangGraph StateGraph]
    GRAPH --> RETRIEVAL[Retrieval port]
    GRAPH --> MODEL[Model gateway]
    RETRIEVAL --> CHROMA[(ChromaDB persistent default)]
    RETRIEVAL -. optional adapter .-> PINECONE[(Pinecone)]
    MODEL -. optional .-> NIM[NVIDIA NIM]
    INGEST[Ingestion service] --> RETRIEVAL
    DOCS[Internal documents] --> INGEST
~~~

## Runtime boundaries

| Boundary | Responsibility | Must not do |
| --- | --- | --- |
| FastAPI/API | Validate requests, expose versioned operations, map application results to stable response schemas | Embed retrieval or model-provider details in route handlers. |
| Application service | Coordinate query/ingest use cases and return typed results | Depend directly on browser concerns. |
| LangGraph workflow | Route, retrieve, grade evidence, rewrite within a fixed bound, synthesize, and record trace events | Pretend a linear sequence of ordinary method calls is a graph. |
| Retrieval adapter | Persist/search chunks and preserve source metadata | Make Pinecone a default or a local-development prerequisite. |
| Model gateway | Select deterministic local behavior or optional NVIDIA NIM calls | Permit ungrounded corporate claims. |
| React/Vite client | Render API data and user-facing states | Reimplement graph routing or invent source data. |

## Grounded query workflow

The V3 graph is a real LangGraph StateGraph with named nodes: supervisor, retrieval, specialist, grade, rewrite, synthesize, and fallback.

~~~mermaid
flowchart TD
    START --> supervisor
    supervisor --> retrieval
    retrieval --> specialist
    specialist --> grade
    grade -->|sufficient evidence| synthesize
    grade -->|insufficient & rewrites < 2| rewrite
    rewrite --> retrieval
    grade -->|insufficient & bound reached| fallback
    supervisor -->|explicit web domain| web_research
    web_research --> END
    synthesize --> END
    fallback --> END
~~~

The graph trace is response metadata, not hidden reasoning. It records node-level execution facts such as selected domain, evidence status, and rewrite count. It must not expose private chain-of-thought or secrets.

## Cloud delivery and observability

The first OCI delivery target is a Compute VM running the API/frontend Compose topology. ChromaDB is mounted on durable OCI storage. Runtime AI-provider and LangSmith credentials are supplied from OCI Vault and are never copied into the image or repository.

LangGraph tracing is enabled only when `LANGSMITH_TRACING=true` and a runtime key/project are configured. The provider-specific OpenAI-compatible client is wrapped so a remote synthesis call appears as a nested LangSmith span. Trace inputs and outputs are hidden by default; the deployment owner must approve any payload capture.

## Evidence contract

For corporate requests, the system must either return a source-backed answer or an explicit limitation. A citation record carries the source file, domain, file type, chunk identifier, path, and available page/slide/sheet locator. Citations are derived from retrieved metadata, never fabricated by a model.

External research is not an implicit fallback. It is an explicit route with domain allowlisting and URL citations, and is separate from internal-corpus grounding.

## Persistence and providers

- **Default:** persistent ChromaDB on a writable local/OCI volume.
- **Optional boundary:** Pinecone can be selected through the retrieval port, but the current adapter deliberately fails transparently until a deployment-specific production adapter is supplied.
- **Default model behavior:** deterministic local routing/embedding/synthesis suitable for offline development and tests.
- **Optional model behavior:** NVIDIA NIM only when enabled and credentials are available.
- **Optional observability:** LangSmith for graph and provider traces, with sanitized status and masked payloads by default.

## Migration note

The legacy V1 specification is retained at `docs/legacy/v1-architecture.md`. V3 authority is expressed through `.context`, `.stack`, `dotarchitecture-input.yaml`, `dotarchitecture.yaml`, this document, and the V3 ADRs. The legacy Streamlit/CLI and simulated frontend material are not the V3 product contract while migration is underway.
