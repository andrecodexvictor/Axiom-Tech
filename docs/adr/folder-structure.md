# Proposed Folder Structure

This project is configured to use the **layered** architectural pattern. Agents and developers should organize newly created modules according to the layout below:

```text
src/
├── presentation/          # Controllers, CLI handlers, API endpoints
├── domain/                # Business services, validation and models
└── infrastructure/        # Database repositories, HTTP clients, caches
```

## Compliance Rules
1. Domain files must **never** import files from outer layers (adapters/presentation/infrastructure).
2. All interface definitions for outgoing dependencies (e.g. database gateways, email servers) must be declared in the inner layers and implemented in outer layers.
