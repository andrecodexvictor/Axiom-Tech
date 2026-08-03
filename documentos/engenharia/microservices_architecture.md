# Axiom Tech - Microservices Architecture & Domain Map

## 1. Domain Overview
Axiom Tech operates a microservices ecosystem organized into bounded contexts:

1. **Identity & Auth Domain (`auth-service`)**:
   - Manages SSO (OAuth2 / OIDC), JWT validation, and RBAC permissions.
2. **Knowledge & RAG Domain (`rag-knowledge-service`)**:
   - Handles multi-format document parsing, Pinecone vector embeddings, and LangGraph multi-agent execution.
3. **Core Platform Services (`platform-core-service`)**:
   - Orchestrates enterprise workflows, customer platform APIs, and automation triggers.
4. **Billing & Subscriptions (`billing-service`)**:
   - Processes customer invoicing, expense tracking, and subscription tiers.

## 2. Service Communication
- **Synchronous**: gRPC for internal service-to-service calls; HTTP/REST for client facing APIs.
- **Asynchronous**: Kafka event streaming for asynchronous event notifications (e.g., `document.uploaded`, `incident.created`).

## 3. Resilience & Rate Limiting
- Circuit breakers implemented via Resilience4j / Tenacity.
- API Gateway (Kong / Traefik) enforces rate limits: 100 requests/minute per client token.
