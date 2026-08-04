# ADR-004: Use a Real LangGraph Workflow

## Status

Accepted — 2026-08-04

## Context

The prior proof of concept described a graph while coordinating agents through ordinary linear method calls. V3 needs observable conditional routing and a bounded grounding loop.

## Decision

Implement orchestration as a compiled LangGraph StateGraph with supervisor, retrieval, specialist, grade, rewrite, synthesize, and fallback nodes. Conditional edges permit at most two rewrites before fallback.

## Consequences

- The graph can emit safe execution metadata for API consumers and tests.
- Evidence failure has an explicit terminal path instead of an invented response.
- Graph state remains typed and bounded; it does not expose private model reasoning.
