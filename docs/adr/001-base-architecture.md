# ADR-001: Base System Architecture

## Context and Problem Statement
We need to define a consistent, scalable architectural style for this project that matches our team size, development speed, and domain complexity.

## Decision Outcome
* Chosen High-Level Architecture: **modular-monolith**
* Chosen Internal Design Pattern: **layered-with-ports-at-integration-seams**

### Rationale
* The selected architecture matches our constraints.
* Alternative high-level options were rejected to avoid over-engineering or integration overhead.

## Rejected Options and Trade-offs
* **monolith**: Um monólito seria um gargalo para a velocidade de entrega do time, deploy desacoplado ou escalabilidade horizontal.
* **microservices**: Rejeitado devido ao alto custo operacional. Recomendado apenas para times grandes (>= 15 membros) com alta complexidade.
* **event-driven**: Sistemas orientados a eventos trazem complexidade de tracing e consistência eventual que não são justificadas neste escopo.
* **serverless**: Estruturas serverless criam alto acoplamento com provedores de nuvem e gargalos de cold start que não alinham com o perfil.

## Warnings & Risks
* No immediate over-engineering warnings detected.

## Status
Approved

## Date
2026-08-04
