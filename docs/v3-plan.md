# Axiom Tech Corporate AI Agent — V3 Delivery Plan

## Outcome

Turn the current proof of concept into a locally runnable, testable corporate knowledge assistant whose answers are grounded in the repository's internal documents and whose architecture can be deployed to OCI.

## Architecture decisions

- Use a modular monolith. Keep the graph, retrieval, ingestion, model gateway, API, and UI independently replaceable without introducing distributed-system overhead.
- Make ChromaDB the default persistent vector store for local development and OCI volumes. Keep Pinecone behind an optional adapter instead of making a paid external service a runtime requirement.
- Expose the application through FastAPI. The React/Vite interface and CLI consume the same application service contract.
- Build the orchestration with an actual LangGraph `StateGraph`: supervisor, retrieval, relevance grading, bounded query rewrite, grounded synthesis, and explicit fallback.
- Keep corporate answers internal-only by default. External research is an explicit route and must use an allowlist and URL citations.
- Return structured citations with source, domain, file type, chunk, and page/section when available.
- Provide deterministic offline behavior so ingestion, retrieval, routing, and citations can be tested without NVIDIA or Pinecone credentials.

## Delivery slices

1. Governance and contracts
   - Update DotContext, DotArchitecture, and DotStack specifications for V3.
   - Add ADRs for ChromaDB-first storage, LangGraph orchestration, and the API boundary.
   - Capture product and UI principles in `PRODUCT.md` and `DESIGN.md`.

2. Backend foundation
   - Add typed settings and environment validation.
   - Introduce vector-store and model-gateway ports.
   - Implement persistent ChromaDB plus deterministic local embeddings.
   - Preserve an optional Pinecone adapter boundary.
   - Make ingestion idempotent and report per-file outcomes.

3. Agentic RAG
   - Implement domain routing for HR, legal, engineering, repository, and web research.
   - Retrieve with domain-aware filters.
   - Grade evidence, rewrite at most twice, and refuse unsupported corporate claims.
   - Synthesize concise answers with traceable citations and execution metadata.

4. Product interface
   - Replace the simulated V2 response with a typed API client.
   - Build an accessible, responsive knowledge workspace with clear loading, error, empty, answer, source, and system-status states.
   - Provide suggested corporate questions and an explicit reindex action.

5. Quality and delivery
   - Add unit, integration, API, and frontend tests.
   - Add Docker assets suitable for OCI Compute/Container Instances.
   - Update setup, architecture, environment, API, and demo documentation.
   - Run Python tests, frontend tests/build, architecture verification, and stack audit before committing.

6. Go-live and challenge evidence
   - Use OCI Compute as the first deployable target with durable Chroma storage.
   - Keep NVIDIA, web-research, and LangSmith credentials in OCI Vault/runtime configuration.
   - Verify health, ingestion, grounded citations, restart persistence, and LangSmith trace delivery.
   - Add a sanitized online screenshot or video to README after the deployment is actually reachable.

## Acceptance criteria

- `POST /api/v1/query` returns a grounded answer, domain, specialist, sources, and graph trace.
- `POST /api/v1/ingest` indexes every supported fixture format without duplicating existing chunks.
- The app works without cloud credentials using local ChromaDB and deterministic model fallbacks.
- Corporate queries with no adequate evidence return a clear, non-hallucinated limitation.
- The React interface calls the real API and passes accessibility and responsive smoke checks.
- Automated tests and production builds pass from a clean checkout.
- Architecture, context, stack, README, and environment examples describe the implementation rather than an aspirational system.
- The OCI URL and online execution evidence are recorded before claiming challenge completion.
