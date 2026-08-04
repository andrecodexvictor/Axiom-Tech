# ADR 006: OCI Compute First Go-Live with Vault and LangSmith

## Status

Accepted as the first deployment path. This is a deployment decision, not evidence that production resources already exist.

## Context

The Alura Agentes challenge requires the agent to run using at least one OCI service and requires a screenshot or video of the online execution. Axiom Tech V3 uses persistent ChromaDB by default, two cooperating containers, explicit ingestion, optional NVIDIA inference, and LangGraph orchestration. Production credentials must be available at runtime without being committed.

## Decision

Use an OCI Compute VM as the first go-live target and run the existing Docker Compose topology on it. Attach an OCI Block Volume for `/data/chroma`, store provider and LangSmith credentials in OCI Vault, and grant the VM a narrowly scoped dynamic-group permission to read the runtime secret bundle. Use the Oracle `oci-cloud-mcp-server` for read-before-write discovery and OCI SDK operations.

Enable LangSmith only through runtime variables. LangGraph traces are automatic when enabled; the provider-specific OpenAI-compatible client is wrapped so remote model calls appear as nested spans. Inputs and outputs are hidden by default to reduce accidental transfer of internal questions and corpus content.

## Alternatives considered

- **OCI Container Instances:** simpler container hosting, but the default ChromaDB persistence requirement makes ephemeral writable storage unsafe for the first target.
- **OKE:** suitable for later horizontal scaling, but introduces cluster, ingress, storage, and operational complexity beyond the challenge’s first proof.
- **OCI Functions:** not a fit for the long-running API, persistent local index, and two-container proxy topology.
- **Build-only on the VM:** acceptable for the first smoke test; OCIR remains the preferred next step for immutable image delivery.

## Consequences

Positive:

- Meets the OCI-service requirement with a small operational surface.
- Preserves the current Compose topology and durable Chroma index.
- Keeps AI and observability keys outside Git and images.
- Provides a reversible release/tag and volume rollback path.

Trade-offs:

- A single VM is not high availability.
- The first public smoke test may use port 8080 until a TLS load balancer is added.
- Vault secret materialization creates a protected runtime file on the VM; rotation must recreate the file and restart the API.
- LangSmith is an external observability boundary. Retention, region, access, and payload masking must be reviewed before enabling unmasked traces.

## Follow-up before a hardened production service

1. Push immutable API/frontend images to OCIR from CI.
2. Put TLS termination and a health-checked load balancer in front of the VM or move to a managed orchestration target.
3. Replace single-volume Chroma with a backup/restore plan or a managed vector database appropriate to the corpus.
4. Add OCI logging/metrics and an alert for health failures, latency, provider errors, and disk usage.
5. Define LangSmith retention and redaction policy with the data owner.
