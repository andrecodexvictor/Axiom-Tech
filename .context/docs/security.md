---
type: doc
name: security
description: Axiom Tech data, provider, and retrieval safety rules
category: security
generated: 2026-08-04
status: filled
scaffoldVersion: "2.0.0"
---

# Security

- Keep credentials in `.env` or deployment secrets; commit only `.env.example`.
- Never place source content, credentials, or model hidden reasoning in logs, status responses, screenshots, or citations.
- Validate ingestion paths against `AXIOM_DOCUMENTS_DIR` before reading files.
- Web research is opt-in, HTTPS-only, allowlist-only, bounded by time/size, and rejects unsafe hosts/URLs.
- Treat HR, legal, and incident answers as informational retrieval; route approvals and escalations to document owners.
- A configured provider must fail clearly when unavailable. The service must not claim cloud persistence or fabricate citations.
