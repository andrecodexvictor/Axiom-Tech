# ADR-003: ChromaDB-First Retrieval Storage

## Status

Accepted — 2026-08-04

## Context

V3 needs persistent retrieval storage that works from a clean local checkout and can survive OCI container restarts when backed by a volume. Requiring a paid external service would make development and deterministic tests fragile.

## Decision

Use persistent **ChromaDB** as the default vector store. Keep **Pinecone** behind a retrieval adapter and enable it only through explicit configuration and valid credentials.

## Consequences

- Local and OCI-volume workflows have a no-secret default.
- Tests can exercise ingestion/retrieval deterministically.
- The storage path must be writable and persisted in container deployments.
- Pinecone has a deliberately isolated adapter boundary. Until a deployment-specific adapter is completed, selecting it fails transparently instead of silently indexing nowhere.
