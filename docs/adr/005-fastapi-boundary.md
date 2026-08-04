# ADR-005: FastAPI as the V3 Application Boundary

## Status

Accepted — 2026-08-04

## Context

V3 replaces a UI-coupled proof of concept with a React/Vite client and needs one stable integration point for browser, CLI, tests, and deployment probes.

## Decision

Expose query, ingestion, health, and status operations through versioned FastAPI routes under /api/v1. Route handlers validate and translate requests; application and graph logic remain behind the boundary.

## Consequences

- The React client does not import backend or graph internals.
- OCI/container probes have a clear health endpoint.
- API responses can evolve deliberately while V1 contracts remain isolated.
- CORS and operational configuration are centralized at the boundary.
