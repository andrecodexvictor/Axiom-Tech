"""HTTP request/response models for the versioned API."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    domain: Optional[Literal["rh", "juridico", "engenharia", "api_spec", "web"]] = None
    top_k: int = Field(4, ge=1, le=10)


class IngestRequest(BaseModel):
    path: Optional[str] = Field(None, max_length=4096)


class CitationResponse(BaseModel):
    id: str
    source: str
    domain: str
    file_type: str
    chunk_id: str
    chunk_index: int
    score: float
    path: Optional[str] = None
    url: Optional[str] = None
    page: Optional[int] = None
    slide: Optional[int] = None
    sheet: Optional[str] = None


class TraceResponse(BaseModel):
    node: str
    event: str
    details: str


class QueryResponse(BaseModel):
    answer: str
    domain: str
    specialist: str
    citations: List[CitationResponse]
    trace: List[TraceResponse]
    rewrite_count: int
    grounded: bool


class IngestFileResponse(BaseModel):
    source: str
    status: str
    chunks: int
    message: Optional[str] = None


class IngestResponse(BaseModel):
    received: int
    inserted: int
    updated: int
    unchanged: int
    skipped: int
    files: List[IngestFileResponse]


class HealthResponse(BaseModel):
    status: str
    version: str


class VectorStoreStatusResponse(BaseModel):
    backend: str
    collection: str
    document_count: int


class ModelStatusResponse(BaseModel):
    gateway: str
    remote_enabled: bool
    model: Optional[str] = None


class WebResearchStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    allowlist_hosts: int


class ObservabilityStatusResponse(BaseModel):
    provider: str
    enabled: bool
    configured: bool
    project: str
    inputs_hidden: bool
    outputs_hidden: bool


class StatusResponse(BaseModel):
    status: str
    version: str
    vector_store: VectorStoreStatusResponse
    models: ModelStatusResponse
    documents_dir: str
    web_research: Optional[WebResearchStatusResponse] = None
    observability: Optional[ObservabilityStatusResponse] = None
