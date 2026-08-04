# Axiom Tech Corporate Knowledge Assistant — Product Brief (V3)

## Product status

This file is the V3 product contract. It describes the intended local and OCI-ready product surface; it is not evidence of a production deployment, a published demo, or a captured screenshot.

## Platform

web

## Product register

Task-focused internal knowledge workspace.

## Problem

Employees need reliable answers from internal policies, engineering guidance, incident procedures, legal material, and repository/API references. Searching across files is slow, and an ungrounded answer is worse than no answer.

## Users and jobs

| User | Job to be done | Required outcome |
| --- | --- | --- |
| Employee | Find an internal policy or onboarding answer | A concise answer with traceable source citations. |
| Engineer or operations lead | Resolve a process, incident, architecture, or API question | Domain-aware evidence and an explicit limitation when evidence is weak. |
| HR or legal stakeholder | Check an authoritative internal document | No invented policy; source and locator remain visible. |
| Knowledge administrator | Refresh the local corpus | An explicit ingestion action and a per-file outcome, without silently duplicating data. |

## V3 outcome

V3 turns the proof of concept into a modular-monolith knowledge assistant with a React/Vite client and a FastAPI boundary. Every corporate answer is either grounded in retrieved internal evidence or clearly marked as unsupported. Local development must remain deterministic and useful without NVIDIA NIM or Pinecone credentials.

## Product principles

1. **Evidence before eloquence.** Cite the internal source, domain, file type, chunk, and page or section when available.
2. **Honest uncertainty.** If retrieval cannot support a corporate claim, say so plainly and direct the user to an appropriate source or owner.
3. **Internal by default.** Corporate questions use the indexed internal corpus. External research is an explicit route with URL citations and an allowlist.
4. **One external contract.** The React client and integrations use the versioned HTTP API; the retained migration CLI reuses the same application service rather than duplicating graph logic.
5. **Useful offline.** Deterministic routing, embeddings, retrieval, and response fallbacks make development and tests repeatable.

## In scope

- Domain routing for HR, legal/compliance, engineering/operations, repository/API, and explicitly requested external research.
- Persistent local ChromaDB retrieval by default; Pinecone only through an optional adapter.
- A real LangGraph workflow with evidence grading, at most two rewrite attempts, grounded synthesis, and a visible execution trace.
- Query, ingestion, health, and status API operations.
- An accessible React/Vite workspace that presents answers, sources, system state, errors, and empty states.

## Out of scope for V3

- A claim that the service is deployed to OCI or production.
- Autonomous external browsing for ordinary corporate questions.
- Replacing source-document ownership, approval workflows, or legal/HR review.
- Multi-service decomposition, distributed orchestration, or a paid vector/LLM service as a prerequisite for local use.

## Success signals

- A user can distinguish an evidence-backed answer from an unsupported request without reading implementation details.
- Source citations make the answer auditable and lead back to the originating document.
- A clean checkout can exercise the primary path without cloud secrets.
- Re-indexing is deliberate, observable, and does not duplicate unchanged chunks.
