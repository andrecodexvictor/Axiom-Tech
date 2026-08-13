# ADR-008: Version Embedding Spaces and Rerank Vector Candidates

## Status

Accepted — 2026-08-10

## Context

Chroma accepts caller-supplied vectors but cannot infer whether two writes came from compatible providers, models, dimensions, or normalization rules. Silently changing any of those values can corrupt retrieval while the collection still appears healthy. At the same time, a full independent lexical engine or heavyweight cross-encoder would add operational dependencies that V3 does not need.

## Decision

Define a provider-neutral embedding port with validated dimensions and a sanitized status contract. Support:

- explicitly selected deterministic lexical hashing for offline development/tests;
- explicitly configured OpenAI-compatible real embeddings for semantic retrieval;
- disabled/fail-closed operation when requested.

Never fall back between embedding providers after a request failure. Compute a fingerprint from the complete vector-space contract, suffix the physical Chroma collection with that fingerprint, and validate protected collection metadata before reads or writes. A changed fingerprint requires explicit reingestion.

Retrieve more vector candidates than the requested answer limit, then apply lexical reranking, a configurable minimum score, and bounded MMR diversity. Describe this honestly as post-retrieval reranking, not hybrid search.

## Consequences

- Provider/model/dimension upgrades cannot mix incompatible vectors.
- Reindexing is deliberate and observable; old physical collections remain recoverable until an operator removes them.
- Remote embedding outages fail ingestion/query instead of silently changing answer behavior.
- Exact policy names and identifiers receive a pragmatic lexical boost without adding a second search service.
- Candidate reranking improves diversity, but it is not a substitute for a true lexical index or a trained cross-encoder when future scale/quality requires either.
