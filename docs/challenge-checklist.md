# Alura Agentes Challenge Checklist

This checklist translates the public challenge board into repository evidence. It keeps implementation evidence separate from the cloud proof that must be captured after deployment.

## Required challenge outcomes

| Challenge requirement | Repository evidence | Final proof still needed |
| --- | --- | --- |
| Public GitHub repository | The project is hosted at `https://github.com/andrecodexvictor/Axiom-Tech`. | Keep the repository public and submit its URL through the course workflow. |
| Deploy the agent using at least one OCI service | `docs/oci-mcp-deployment.md` defines an OCI Compute baseline and OCI Vault/Block Volume hardening. | A successful public or reviewer-accessible URL and the OCI resource details. |
| Add an image or video of the cloud execution to the README | README contains a pending evidence row and a safe capture procedure. | Add a sanitized image/video under `docs/evidence/` and link it from README. |

## Functional coverage

| Challenge capability | Implementation | Validation |
| --- | --- | --- |
| PDF extraction | `app/ingestion/loader.py` uses the PDF extractor. | Backend ingestion tests and a production re-index report. |
| Word extraction | `.docx` loader with paragraph/table normalization. | Backend ingestion tests. |
| Excel extraction | `.xlsx` loader with sheet metadata. | Backend ingestion tests. |
| PowerPoint extraction | `.pptx` loader with slide metadata. | Backend ingestion tests. |
| Markdown, CSV, JSON, HTML | Format-aware text normalization and metadata preservation. | Backend ingestion tests. |
| Corporate domains | HR, legal/compliance, engineering, repository/API, and explicit web research. | Query tests and source citations. |
| Grounded answers | LangGraph retrieval, grading, bounded rewrite, synthesis, and fallback. | `POST /api/v1/query` must return citations when `grounded=true`. |
| Functional interface | React/Vite console calls the versioned API and renders answers, citations, trace state, errors, and status. | Frontend check/build plus browser smoke test. |
| Execution record | API health/status, Compose logs, and LangSmith traces when enabled. | Record timestamp, release tag, URL, health response, sample question, and trace project. |

## Evidence capture rules

1. Use a non-sensitive sample question whose answer is supported by a fixture document.
2. Show the browser URL, the answer, and at least one citation in the capture.
3. Do not show API keys, Vault contents, SSH terminals, private IP addresses, confidential corpus text, or raw trace payloads.
4. Keep the capture small and reproducible. A short screen recording is preferable to a large archive.
5. Record the release tag and UTC timestamp in the deployment evidence notes.

The project is not considered challenge-complete until the OCI deployment and the online evidence are both attached to the README.
