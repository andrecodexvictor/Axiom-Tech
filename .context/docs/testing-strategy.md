---
type: doc
name: testing-strategy
description: Axiom Tech backend, frontend, and integration validation
category: testing
generated: 2026-08-04
status: filled
scaffoldVersion: "2.0.0"
---

# Testing Strategy

`tests/backend/` covers the versioned API, settings validation, multi-format extraction, Chroma idempotency, actual LangGraph execution, grounded fallback behavior, language matching, and SSRF-safe web research. Run it with `python -m pytest -q`.

The frontend uses TypeScript compilation and a production Vite build as its static quality gates: `npm --prefix frontend run check` and `npm --prefix frontend run build`. Browser QA should verify desktop layout, 390px mobile width, query submission, error states, citations, and keyboard focus.

Before release, also run `python -m compileall -q app`, `pip check`, `docker compose config --quiet`, `git diff --check`, and a secret-pattern scan that excludes local `.env` files.
