# ADR-003: ChromaDB-First Retrieval Storage

## Status

Accepted — 2026-08-04

## Context

V3 needs persistent retrieval storage that works from a clean local checkout and can survive OCI container restarts when backed by a volume. Requiring a paid external service would make development and deterministic tests fragile.

## Decision

Use persistent **ChromaDB** as the default vector store. Keep **Pinecone** behind a retrieval adapter and enable it only through explicit configuration and valid credentials.

Inject the embedding provider rather than letting Chroma download one implicitly. The clean-checkout development profile explicitly selects deterministic lexical hashing; production may select a real OpenAI-compatible embedding endpoint. Remote embedding errors fail closed and do not fall back to hashing.

Version every physical Chroma collection with a fingerprint covering provider, model, dimension, implementation, normalization, and embedding-contract version. Validate the same values in collection metadata before use. A fingerprint change selects a new empty collection and requires explicit reingestion; it never appends incompatible vectors to an existing collection.

Retrieve an expanded vector candidate set, apply lexical post-reranking and a minimum threshold, then select diverse evidence with bounded MMR. This is intentionally called vector retrieval with lexical reranking, not hybrid search, because V3 has no independent lexical index.

## Consequences

- Local and OCI-volume workflows have a no-secret default.
- Tests can exercise ingestion/retrieval deterministically.
- Embedding/model upgrades are safe but require an explicit reindex, and old physical collections require deliberate lifecycle cleanup.
- Status can report provider/model/dimension/fingerprint and retrieval thresholds without exposing an endpoint, credential, document text, or provider error body.
- The storage path must be writable and persisted in container deployments.
- Pinecone has a deliberately isolated adapter boundary. Until a deployment-specific adapter is completed, selecting it fails transparently instead of silently indexing nowhere.
