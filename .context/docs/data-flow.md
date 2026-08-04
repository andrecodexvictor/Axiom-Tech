---
type: doc
name: data-flow
description: Axiom Tech ingestion and query data flow
category: architecture
generated: 2026-08-04
status: filled
scaffoldVersion: "2.0.0"
---

# Data Flow

## Ingestion

1. `POST /api/v1/ingest` validates that the requested path stays inside `AXIOM_DOCUMENTS_DIR`.
2. `app/ingestion/loader.py` normalizes PDF, DOCX, PPTX, XLSX, CSV, JSON, HTML, Markdown, and text into document records with page/slide/sheet metadata.
3. `app/ingestion/chunker.py` creates stable chunks and deterministic IDs.
4. `KnowledgeService` compares the manifest, removes stale chunks, and upserts only changed records into ChromaDB.
5. The response reports inserted, updated, unchanged, and skipped files.

## Query

```text
employee question -> API schema -> supervisor -> retrieval -> specialist
                 -> grade -> bounded rewrite (at most two) -> synthesis -> citations
```

Internal evidence is retrieved from the configured vector store. The graph returns `grounded=false` with an explicit limitation when evidence is inadequate. The `web` domain is never an automatic fallback: it requires explicit routing, `AXIOM_WEB_RESEARCH_ENABLED`, Serper credentials, and an HTTPS allowlist.

## Data boundaries

- Source files remain under `documentos/`; only normalized chunks and metadata enter the vector store.
- API responses expose source metadata and operational trace events, never credentials or hidden reasoning.
- `.axiom_chroma/`, `.context/cache/`, and `.context/runtime/` are local runtime state and are not committed.
