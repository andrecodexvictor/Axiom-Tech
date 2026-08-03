# Axiom Tech - Back-end Engineering Guidelines

## 1. Overview & Technology Stack
Back-end services at Axiom Tech are built primarily with Python (FastAPI, Asyncio) and Go. All services must be modular, statelessly scalable, and deployable on Kubernetes / OCI GenAI Container instances.

## 2. API Design & Standards
- RESTful APIs must strictly adhere to OpenAPI 3.0 specs.
- Endpoints must follow plural noun conventions: `/api/v1/users`, `/api/v1/documents`, `/api/v1/incidents`.
- Standard JSON response format:
```json
{
  "status": "success",
  "data": {},
  "error": null,
  "timestamp": "2026-08-03T10:00:00Z"
}
```

## 3. Database & Caching
- **Primary Data Store**: PostgreSQL 15+ (Managed OCI Autonomous DB).
- **Caching**: Redis 7.0 for session cache, query result caching, and rate limiting.
- **ORM**: SQLAlchemy 2.0 or Prisma ORM.

## 4. Observability & Logging
- **Structured Logging**: All logs must be output in JSON format with `correlation_id`, `service_name`, and `trace_id`.
- **Metrics**: Prometheus metrics exposed at `/metrics`.
- **Tracing**: OpenTelemetry tracing sent to Jaeger / Grafana Tempo.
