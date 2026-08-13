# LangSmith Observability

## Status

LangGraph emits traces only when LangSmith tracing is explicitly enabled. The graph creates a configured LangSmith client per application configuration and enters a tracing context around the bounded workflow. The OpenAI-compatible model client is also wrapped so a remote synthesis call appears as a nested model span. Deterministic local execution remains available when tracing or provider credentials are absent.

Only operational tags and metadata are added by the graph: workflow version, requested-domain label, `top_k`, vector backend, and embedding fingerprint. Questions, retrieved chunks, answers, prompts, endpoints, and credentials are not added to custom metadata.

## Runtime configuration

Set these values in the OCI runtime secret bundle or local `.env`; never commit them:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<service-key>
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=axiom-tech-v3
LANGSMITH_WORKSPACE_ID=<workspace-id-if-required>
LANGSMITH_HIDE_INPUTS=true
LANGSMITH_HIDE_OUTPUTS=true
```

`LANGSMITH_WORKSPACE_ID` is needed when the key can access more than one workspace. The endpoint changes only for a different LangSmith region or deployment. The project name groups the production traces.

The application accepts the older `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_ENDPOINT`, and `LANGCHAIN_PROJECT` names as configuration fallbacks, but new deployments should use the `LANGSMITH_*` names.

## What the API reports

`GET /api/v1/status` returns a sanitized object like this:

```json
{
  "observability": {
    "provider": "langsmith",
    "enabled": true,
    "configured": true,
    "project": "axiom-tech-v3",
    "inputs_hidden": true,
    "outputs_hidden": true
  }
}
```

The API never returns the LangSmith key or any other provider credential. Vector status similarly exposes only provider/model/dimension/fingerprint plus retrieval strategy/thresholds; it omits the embedding endpoint, credential, persistence path, provider response, and document text.

## Privacy baseline

LangSmith can capture graph state and model prompts. This project defaults `LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true`; the programmatic client replaces those payloads with empty objects before transmission. The first production deployment therefore records timing, graph structure, errors, and sanitized metadata without sending question/document payloads by default. Change those flags only after the data owner has approved the retention, residency, and access model.

Do not place credentials in a question, trace tag, status response, log message, screenshot, or MCP argument. Use a workspace-scoped service key with an expiration/rotation policy where the LangSmith plan supports it.

## Validation

After deployment:

1. Query `/api/v1/status` and confirm `enabled=true`, `configured=true`, and the expected project.
2. Submit one non-sensitive question that is answered by a known corpus document.
3. Open the configured project in LangSmith and confirm a trace contains the graph run and, when NVIDIA mode is enabled, the nested provider call.
4. Confirm hidden inputs/outputs match the approved privacy baseline.
5. If no trace arrives, check outbound HTTPS egress, the endpoint/region, workspace selection, key validity, and container startup logs. Never print the key while diagnosing.

See the [LangSmith LangGraph tracing guide](https://docs.langchain.com/langsmith/trace-with-langgraph) and the [input/output masking guide](https://docs.langchain.com/langsmith/mask-inputs-outputs) for provider-side behavior.
