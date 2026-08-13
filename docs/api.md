# V3 HTTP API Contract

## Status

This is the V3 integration contract for the FastAPI boundary. It is intentionally versioned under /api/v1; clients should not call graph, vector-store, or model-provider modules directly.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /api/v1/health | Cheap process-liveness check suitable for a container probe; it does not call providers. |
| GET | /api/v1/status | Safe runtime status, such as selected local/optional providers and observability state. |
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

## Status

`GET /api/v1/status` reports the selected runtime contracts without making a
billable provider call. A representative response is:

~~~json
{
  "status": "ok",
  "version": "3.0.0",
  "vector_store": {
    "backend": "chroma",
    "collection": "axiom_knowledge",
    "physical_collection": "axiom_knowledge-371ca113a490",
    "document_count": 20,
    "embedding": {
      "provider": "deterministic",
      "model": "axiom-hashing-v2",
      "dimensions": 384,
      "fingerprint": "<sha256-vector-space-fingerprint>",
      "mode": "test-development",
      "configured": true
    },
    "retrieval": {
      "strategy": "vector-candidates+lexical-rerank+mmr",
      "candidate_multiplier": 4,
      "min_score": 0.12,
      "lexical_weight": 0.25,
      "mmr_lambda": 0.75
    }
  },
  "models": {
    "gateway": "deterministic",
    "remote_enabled": false,
    "model": null,
    "fallback": "none",
    "routes": [
      {
        "name": "deterministic",
        "provider": "deterministic",
        "model": null,
        "configured": true,
        "circuit_state": "closed"
      }
    ]
  },
  "documents_dir": "documentos",
  "web_research": {
    "enabled": false,
    "configured": false,
    "allowlist_hosts": 0
  },
  "observability": {
    "provider": "langsmith",
    "enabled": false,
    "configured": false,
    "project": "axiom-tech-v3",
    "inputs_hidden": true,
    "outputs_hidden": true
  }
}
~~~

`status=degraded` means the API process is alive but the configured retrieval
backend is not the persistent Chroma adapter. Changing an embedding provider,
model, dimension, implementation endpoint, or normalization contract selects a
new physical collection and requires explicit ingestion.

The response never returns an API key, endpoint, absolute corpus path,
source-document payload, provider response, or exception message. Model route
entries expose only their name/provider/model, configured state, and in-process
circuit state.

If evidence is inadequate, the API returns a clear non-hallucinated limitation, an empty citation array, grounded=false, and trace metadata showing the fallback outcome. It must not manufacture citations to make the response look complete.

## Ingestion

POST /api/v1/ingest starts a deliberate pass over AXIOM_DOCUMENTS_DIR. Its optional path request field must resolve inside that directory. The result reports received, inserted, updated, unchanged, and skipped counts plus per-file outcomes so an administrator can identify failures. Ingestion is idempotent for unchanged chunks.

## Errors

- Invalid request data returns a validation response; the client retains the user's question for correction.
- An unavailable optional provider must not silently turn into a fabricated answer. In local mode, deterministic fallbacks remain available where configured.
- A configured but unavailable Pinecone adapter fails clearly rather than silently claiming cloud persistence.
