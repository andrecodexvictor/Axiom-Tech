---
type: doc
name: development-workflow
description: Axiom Tech development and review workflow
category: workflow
generated: 2026-08-04
status: filled
scaffoldVersion: "2.0.0"
---

# Development Workflow

Use the repository's PREVC-style flow: plan the boundary, review the ADR/API impact, implement, validate locally, and document the handoff.

## Local checks

```powershell
python -m pytest -q
npm --prefix frontend run check
npm --prefix frontend run build
docker compose config --quiet
git diff --check
```

Keep changes focused. Backend contract changes require updates to `docs/api.md` and tests. Architecture/provider changes require an ADR or an update to the relevant ADR. Frontend changes should preserve keyboard access, responsive behavior, typed API errors, and the citation presentation.

Before a cloud release, validate the challenge checklist, create an immutable release tag, provision or verify OCI resources through the MCP read-before-write flow, place runtime secrets in OCI Vault, and capture the public health/query evidence without sensitive data.

## Pull request gate

Review grounding behavior, secret handling, path/URL validation, ingestion idempotency, and whether optional providers are represented honestly in `/api/v1/status`. Do not commit `.env`, vector persistence, or generated runtime traces.
