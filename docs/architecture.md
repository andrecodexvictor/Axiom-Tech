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
    MODEL -. optional .-> OPENAI[OpenAI API]
    INGEST[Ingestion service] --> RETRIEVAL
    DOCS[Internal documents] --> INGEST
~~~

## Runtime boundaries

| Boundary | Responsibility | Must not do |
| --- | --- | --- |
| FastAPI/API | Validate requests, expose versioned operations, map application results to stable response schemas | Embed retrieval or model-provider details in route handlers. |
| Application service | Coordinate query/ingest use cases and return typed results | Depend directly on browser concerns. |
| LangGraph workflow | Route, retrieve, grade evidence, reformulate within a fixed bound, synthesize, and record trace events | Expose private reasoning or describe the workflow as ReAct when it does not implement a thought/action transcript. |
| Retrieval adapter | Embed, persist/search versioned chunks, rerank candidates, and preserve source metadata | Mix vectors from different providers/models/dimensions or call post-retrieval lexical reranking “hybrid search.” |
| Model gateway | Select explicit deterministic, NVIDIA NIM, or official OpenAI routes with transient-only fallback | Infer a provider from credential presence or permit ungrounded corporate claims. |
| React/Vite client | Render API data and user-facing states | Reimplement graph routing or invent source data. |

## Grounded query workflow

The V3 graph is a real LangGraph `StateGraph` with named nodes: supervisor, retrieval, specialist, grade, rewrite, synthesize, and fallback. It permits one initial retrieval and at most two reformulated retrieval actions. An explicitly requested internal domain is never widened; for an automatically inferred domain only, the final bounded action may search all internal domains before refusing.

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

The graph trace is operational response metadata, not hidden reasoning. It records only node/event names, bounded step counts, retrieval scope, candidate counts, and aggregate coverage/relevance. Questions, document text, prompts, credentials, and chain-of-thought are not copied into trace details. This is therefore described as a grounded LangGraph retrieval workflow, not as ReAct.

## Embedding and retrieval contract

The embedding provider is injected behind the vector-store boundary:

- `deterministic` is the explicit local/test vector space used by the clean-checkout profile. It is lexical hashing, not a semantic model.
- `openai` uses a configured OpenAI-compatible embeddings endpoint and validates batch order, dimension, finite values, and non-zero vectors. A provider error fails closed; it never falls back to hashing because that would silently change vector space.
- `disabled` keeps the API/status surface available while ingestion and internal retrieval fail closed.

Every embedding contract has a SHA-256 fingerprint over provider, model, dimensions, implementation, normalization, and contract version. Chroma stores data in a physical collection named from the logical collection plus the fingerprint suffix and validates matching metadata at startup. Changing provider, model, dimensions, endpoint implementation, or normalization selects an empty physical collection; the operator must run explicit ingestion. The old collection is retained until a deliberate cleanup, so incompatible vectors are never mixed.

Search uses expanded vector candidates, then a lightweight lexical rerank, a minimum relevance threshold, and bounded MMR selection to reduce near-duplicate chunks. It is not hybrid retrieval because there is no independent lexical index. The sanitized status endpoint reports the active strategy and thresholds.

Ingestion normalizes Unicode/newlines, uses corpus-relative source keys, and records document/content hashes, chunk count/index, character spans, word count, section heading, and page/slide/sheet locators. These fields make idempotent reingestion and citations auditable without putting document text into status or operational traces.

## Cloud delivery and observability

The first OCI delivery target is a Compute VM running the API/frontend Compose topology. ChromaDB is mounted on durable OCI storage. Runtime AI-provider and LangSmith credentials are supplied from OCI Vault and are never copied into the image or repository.

LangGraph tracing is enabled only when `LANGSMITH_TRACING=true` and a runtime key/project are configured. Each graph invocation uses a programmatic LangSmith client/context and only sanitized tags/metadata; graph inputs and outputs are replaced with empty objects by default. The provider-specific OpenAI-compatible client is wrapped so a remote synthesis call appears as a nested LangSmith span. The deployment owner must approve any payload capture.

## Evidence contract

For corporate requests, the system must either return a source-backed answer or an explicit limitation. A citation record carries the source file, domain, file type, chunk identifier, path, and available page/slide/sheet locator. Citations are derived from retrieved metadata, never fabricated by a model.

External research is not an implicit fallback. It is an explicit route with domain allowlisting and URL citations, and is separate from internal-corpus grounding.

## Persistence and providers

- **Default:** persistent ChromaDB on a writable local/OCI volume.
- **Optional boundary:** Pinecone can be selected through the retrieval port, but the current adapter deliberately fails transparently until a deployment-specific production adapter is supplied.
- **Default local behavior:** deterministic routing, lexical hashing embeddings, and synthesis suitable for offline development and tests. Production can select real OpenAI-compatible embeddings explicitly; provider failures do not downgrade vector space.
- **Optional model behavior:** NVIDIA NIM or the official OpenAI API only through an explicit, complete route; remote fallback advances only after transient failures.
- **Optional observability:** LangSmith for graph and provider traces, with sanitized status and masked payloads by default.

## Migration note

The legacy V1 specification is retained at `docs/legacy/v1-architecture.md`. V3 authority is expressed through `.context`, `.stack`, `dotarchitecture-input.yaml`, `dotarchitecture.yaml`, this document, and the V3 ADRs. The legacy Streamlit/CLI and simulated frontend material are not the V3 product contract while migration is underway.
