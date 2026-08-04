---
type: doc
name: tooling
description: Axiom Tech commands, providers, and dotcontext integration
category: tooling
generated: 2026-08-04
status: filled
scaffoldVersion: "2.0.0"
---

# Tooling

- Python dependencies are declared in `requirements.txt` and `pyproject.toml`; the supported target is Python 3.11+.
- Frontend dependencies and scripts are under `frontend/package.json`; the root scripts delegate with `npm --prefix frontend`.
- `Dockerfile` runs the API and builds the frontend; `docker-compose.yml` adds the Nginx static/API proxy.
- `frontend/pnpm-workspace.yaml` must declare `packages: - .`; the CI install uses pnpm with a frozen lockfile.
- `.context/` is managed by the local dotcontext MCP binary pinned in the Codex config. Use `context` actions with `repoPath` set to the Axiom Tech root.
- `.stack`, `dotarchitecture.yaml`, and `dotarchitecture-input.yaml` are the versioned architecture/tooling decisions; `docs/adr/` records why they exist.
- The Oracle OCI Cloud MCP server is configured outside the repository with `uvx oracle.oci-cloud-mcp-server@latest`; deployment actions follow discovery, description, and invocation.
