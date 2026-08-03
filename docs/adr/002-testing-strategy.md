# ADR-002: Development Style and Testing Strategy

## Context and Problem Statement
We need to establish clear testing guidelines and engineering processes to ensure codebase reliability and speed up onboarding.

## Decision Outcome
* Recommended Development Styles:
* BDD (Behavior-Driven Development) ou alta cobertura de testes unitários/integração
* Trunk-Based Development com branchs de features curtas (< 1 dia)
* Pipelines de Integração Contínua com gates de validação nos Pull Requests

* Observability and Deployment Guidelines:
* Application Performance Monitoring (APM) para acompanhar gargalos de rota e consumo de CPU
* Rotação e agregação local de logs
* Deploy Rolling Update simples ou Blue-Green básico

## Status
Approved

## Date
2026-08-03
