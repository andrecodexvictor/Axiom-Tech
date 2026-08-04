---
type: doc
name: project-overview
description: Axiom Tech V3 product and repository overview
category: overview
generated: 2026-08-04
status: filled
scaffoldVersion: "2.0.0"
---

# Project Overview

Axiom Tech is a fictional technology company with an internal corporate knowledge assistant. Employees ask natural-language questions about engineering, operations, legal/compliance, HR, and repository/API documentation. The V3 product responds with concise, source-cited answers through a single React console.

The repository is a Python modular monolith: FastAPI is the boundary, LangGraph is the orchestration runtime, ChromaDB is the local vector bank, and NVIDIA NIM/Pinecone are optional hosted integrations. The supported corpus lives in `documentos/` and is normalized through the multi-format ingestion pipeline.

Start with [README.md](../../README.md), the [V3 plan](../../docs/v3-plan.md), and the [API contract](../../docs/api.md).
