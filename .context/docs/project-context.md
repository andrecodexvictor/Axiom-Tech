# DotContext Specification: Axiom Tech V3 Context and Knowledge Governance

## Status

This is the V3 domain and answer-governance contract. The retained `docs/legacy/v1-architecture.md` file documents the legacy V1 topology and is not the current V3 authority.

## Mission

Axiom Tech provides employees with concise, reliable answers from internal corporate knowledge. The system reduces search friction without replacing the source document, policy owner, legal review, or incident command process.

## Users and response style

- **Users:** employees, engineering/operations leads, HR, legal/compliance stakeholders, and knowledge administrators.
- **Assistant role:** corporate knowledge assistant, not a policy approver or autonomous decision-maker.
- **Style:** answer first; use short, plain language; include only evidence-backed detail; expose citations immediately.
- **Language:** support the language of the question and preserve authoritative source names/locators.

## Knowledge boundary

1. **Internal corpus by default.** Corporate questions use indexed files under the configured documents directory.
2. **External research by exception.** It requires an explicit route, an allowlist, and URL citations. It is not an automatic fallback when internal evidence is weak.
3. **No evidence, no claim.** If retrieved evidence cannot support a corporate answer, return a clear limitation and, when helpful, name the appropriate source owner or next step.
4. **No fabricated citations.** Sources are derived from retrieval metadata, not generated prose.

## Supported business domains

| User-facing domain | Corpus examples | Retrieval metadata |
| --- | --- | --- |
| People and operations | onboarding, benefits, home-office, internal communication | rh, comunicacao |
| Legal and compliance | terms of use, privacy, LGPD | juridico |
| Engineering and incident response | backend guidance, architecture, resilience/SEV procedures | engenharia |
| Repository and API reference | internal API contracts and repository-oriented material | api_spec |
| Strategy | planning/roadmap material when deliberately indexed | estrategico |

The router may use stable V3 labels such as hr, legal, engineering, repository, or external_research while preserving the original corpus domain in citations.

## Citation and answer contract

An evidence-backed answer includes:

- source filename;
- corpus domain;
- file type;
- chunk identifier;
- page, slide, or sheet locator when extraction provides one.

Responses also include safe execution metadata: selected domain/specialist, graph nodes traversed, rewrite count, and whether grounding passed. This trace is operational metadata, never private model reasoning.

## Safety and data handling

- Do not send internal content to an optional external model/provider unless that provider is intentionally enabled by the deployment owner.
- Never place credentials, source-document contents, or hidden reasoning in logs, API status responses, citations, screenshots, or repository documentation.
- Treat legal, HR, and incident content as informational retrieval. Direct users to owners or authoritative procedures for actions requiring approval or escalation.
- Ingestion must retain source metadata and report failures; it must not silently discard unreadable input.

## Quality gates

- Internal answers cite retrieved evidence or clearly state insufficient evidence.
- The query rewrite loop is bounded to two attempts.
- Local deterministic behavior covers routing, embeddings, retrieval, citations, and fallback answers without cloud credentials.
- Corpus refresh is an explicit administrative action with per-file outcomes.

## Challenge and go-live context

The Alura Agentes challenge requires a public GitHub repository, an online deployment using at least one OCI service, and a screenshot or video proving the online execution. The repository must not claim the last two outcomes until a real URL, grounded answer, and sanitized capture have been verified.

The first deployment target is an OCI Compute VM running the existing Compose topology. ChromaDB requires durable writable storage, so the cloud profile uses an OCI Block Volume and keeps provider/LangSmith credentials in OCI Vault. The Oracle OCI Cloud MCP server is used for read-before-write resource discovery and OCI SDK operations.

LangSmith is an opt-in observability boundary. LangGraph traces and wrapped provider spans are enabled only with runtime configuration. Inputs and outputs are hidden by default because traces can contain questions, prompts, and retrieved corpus content.
