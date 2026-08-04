# V3 HTTP API Contract

## Status

This is the V3 integration contract for the FastAPI boundary. It is intentionally versioned under /api/v1; clients should not call graph, vector-store, or model-provider modules directly.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /api/v1/health | Liveness/readiness check suitable for a container probe. |
| GET | /api/v1/status | Safe runtime status, such as selected local/optional providers. |
| POST | /api/v1/query | Run the grounded query workflow. |
| POST | /api/v1/ingest | Explicitly index the configured internal corpus. |

## Query

POST /api/v1/query

~~~json
{
  "question": "Como devo responder a um incidente SEV-1?",
  "domain": "engenharia",
  "top_k": 4
}
~~~

The response is typed JSON. Its stable concepts are an answer, selected domain/specialist, source citations, and a safe execution trace:

~~~json
{
  "answer": "...",
  "domain": "engineering",
  "specialist": "engineering",
  "citations": [
    {
      "id": "...",
      "source": "incident_resilience_manual.md",
      "domain": "engenharia",
      "file_type": ".md",
      "chunk_id": "...",
      "chunk_index": 0,
      "score": 0.82,
      "path": "documentos/engenharia/incident_resilience_manual.md"
    }
  ],
  "trace": [
    {
      "node": "supervisor",
      "event": "routed",
      "details": "Routed to engineering_operations"
    }
  ],
  "rewrite_count": 0,
  "grounded": true
}
~~~

The optional query domain is one of rh, juridico, engenharia, api_spec, or web; top_k is between 1 and 10. The `web` domain is explicit and fail-closed: it makes no outbound request unless web research, a Serper credential, and an HTTPS hostname allowlist are all configured. Internal citations may carry page, slide, sheet, and a corpus-relative path; verified external citations carry a URL. Clients must tolerate an empty citation array and missing optional locators. The trace contains execution metadata only; it is not a model chain-of-thought.

If evidence is inadequate, the API returns a clear non-hallucinated limitation, an empty citation array, grounded=false, and trace metadata showing the fallback outcome. It must not manufacture citations to make the response look complete.

## Ingestion

POST /api/v1/ingest starts a deliberate pass over AXIOM_DOCUMENTS_DIR. Its optional path request field must resolve inside that directory. The result reports received, inserted, updated, unchanged, and skipped counts plus per-file outcomes so an administrator can identify failures. Ingestion is idempotent for unchanged chunks.

## Errors

- Invalid request data returns a validation response; the client retains the user's question for correction.
- An unavailable optional provider must not silently turn into a fabricated answer. In local mode, deterministic fallbacks remain available where configured.
- A configured but unavailable Pinecone adapter fails clearly rather than silently claiming cloud persistence.
