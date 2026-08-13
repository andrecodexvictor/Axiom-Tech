# ADR-004: Use a Real LangGraph Workflow

## Status

Accepted — 2026-08-04

## Context

The prior proof of concept described a graph while coordinating agents through ordinary linear method calls. V3 needs observable conditional routing and a bounded grounding loop.

## Decision

Implement orchestration as a compiled LangGraph `StateGraph` with supervisor, retrieval, specialist, grade, rewrite, synthesize, and fallback nodes. Conditional edges permit one initial retrieval plus at most two reformulated retrieval actions before fallback. The final action may widen an automatically inferred internal domain, but an explicitly requested domain is never widened.

Do not label the workflow ReAct or expose thought text. Its trace is operational metadata: node/event, bounded step, retrieval scope/candidate count, and aggregate evidence scores. Deterministic/hash retrieval requires direct lexical evidence before synthesis; semantic-only passage is allowed only for an explicitly configured remote semantic embedding provider above its relevance threshold.

## Consequences

- The graph can emit safe execution metadata for API consumers and tests.
- Evidence failure has an explicit terminal path instead of an invented response.
- Graph state remains typed and bounded; it does not expose private model reasoning.
- Runtime recursion is capped independently of the rewrite counter.
- LangSmith receives sanitized tags/metadata and hides graph inputs/outputs by default.
