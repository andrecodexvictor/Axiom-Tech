# ADR 007: Explicit and fail-closed model provider routing

## Status

Accepted.

## Context

The V3 gateway previously inferred a single NVIDIA route from an enable flag and
credential, created an OpenAI-compatible client without an application timeout,
and converted every provider failure into a deterministic answer. That kept local
development available, but it made authentication errors, invalid requests, rate
limits, and network outages indistinguishable. Kimi and MiniMax credentials were
loaded but did not participate in the V3 gateway.

OCI remains the deployment boundary recorded in ADR 006. The repository has no
OCI Generative AI authentication adapter, so this decision does not claim or
simulate one. NVIDIA NIM and the official OpenAI API are both accessed through the
existing OpenAI-compatible SDK boundary.

## Decision

Model routing is an ordered, startup-validated registry:

- `AXIOM_LLM_PROVIDER` selects `deterministic`, `nvidia`, or `openai`.
- `AXIOM_LLM_FALLBACK` selects `deterministic` or `none` for a single remote
  provider.
- `AXIOM_LLM_ROUTES` is the mutually exclusive advanced form. It defines the
  complete priority order and may include `nvidia`, `openai`,
  `nvidia-kimi`, `nvidia-minimax`, `nvidia-deepseek`, and a final
  `deterministic` route.

Credentials never select a route by their presence. Every selected remote route
must have an HTTPS endpoint, a bounded model identifier, and its matching key.
The official OpenAI endpoint is the default; sending an OpenAI key to a different
HTTPS endpoint additionally requires `AXIOM_OPENAI_ALLOW_CUSTOM_BASE_URL=true`.
Invalid explicit configuration stops startup with an error that names fields or
routes but never their values.

The NVIDIA model-specific routes retain the models and keys already represented
by the project. They all use the configured NVIDIA NIM endpoint; no third-party
Kimi, MiniMax, or DeepSeek endpoint is inferred. The legacy
`AXIOM_NVIDIA_ENABLED` selector remains supported when no new selector is set,
and `DEEPSEEK_API_KEY` remains the fallback credential for the generic NVIDIA
route. Existing `NvidiaGateway` imports remain an alias for the provider-neutral
gateway.

Each SDK client receives the bounded `AXIOM_LLM_TIMEOUT_SECONDS` and
`AXIOM_LLM_MAX_RETRIES` values. After SDK retries are exhausted, the registry
advances only for connection failures, timeouts, rate limits, HTTP 408/409, or
5xx responses. Authentication, authorization, invalid requests, and malformed or
empty successful responses stop immediately. Consecutive transient failures open
an in-memory circuit for that route; a bounded recovery interval permits a
half-open probe. The circuit is process-local and deliberately carries no
credential or provider-response data.

`GET /api/v1/health` remains a cheap process liveness endpoint and does not make
billable or secret-bearing provider calls. `GET /api/v1/status` retains
`models.gateway`, `models.remote_enabled`, and `models.model`, and adds the
configured fallback plus sanitized per-route name, provider, model, configured
state, and circuit state. It never returns keys, endpoints, provider bodies, or
exception messages.

## Consequences

Positive:

- Provider/model/key selection is deterministic and reviewable from configuration.
- A typo or incomplete explicit remote route cannot silently send a credential to
  another provider or quietly change answer mode.
- Local deterministic behavior remains the no-secret default and can be an
  explicit transient-only fallback for OCI deployments.
- Operational status distinguishes route configuration and circuit health without
  becoming a credential oracle.

Trade-offs:

- Non-transient provider errors now surface through the existing generic query
  `503` instead of producing a local answer.
- Circuit state is per process; a multi-worker deployment does not share it.
- Model availability is not probed by health/status. A separate authenticated,
  rate-limited readiness workflow would be required if active provider probes are
  later needed.
- Adding OCI Generative AI requires a dedicated authentication adapter and ADR;
  an OpenAI-shaped endpoint alone is not treated as sufficient proof of OCI
  compatibility.
