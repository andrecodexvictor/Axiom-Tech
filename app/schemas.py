"""HTTP request/response models for the versioned API."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    domain: Optional[Literal["rh", "juridico", "engenharia", "api_spec", "web"]] = None
    top_k: int = Field(4, ge=1, le=10)


class IngestRequest(BaseModel):
    path: Optional[str] = Field(None, max_length=4096)
    force: bool = False


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
    duration_ms: float = 0.0
    timings_ms: Dict[str, float] = Field(default_factory=dict)


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


class SourceStatusResponse(BaseModel):
    path: str
    domain: str
    file_type: str
    size_bytes: int
    modified_at: str
    indexed_chunks: int
    expected_chunks: int
    status: str
    message: Optional[str] = None


class SourcesResponse(BaseModel):
    total: int
    indexed: int
    pending: int
    sources: List[SourceStatusResponse]


class SourcePreviewResponse(BaseModel):
    path: str
    domain: str
    file_type: str
    size_bytes: int
    modified_at: str
    content: str
    extracted_sections: int
    truncated: bool


class HealthResponse(BaseModel):
    status: str
    version: str


class VectorStoreStatusResponse(BaseModel):
    backend: str
    collection: str
    physical_collection: Optional[str] = None
    document_count: int
    source_count: Optional[int] = None
    ready: bool = False
    reason: Optional[str] = None
    embedding: Optional["EmbeddingStatusResponse"] = None
    retrieval: Optional["RetrievalStatusResponse"] = None


class EmbeddingStatusResponse(BaseModel):
    provider: str
    model: Optional[str] = None
    dimensions: int
    fingerprint: str
    mode: str
    configured: bool


class RetrievalStatusResponse(BaseModel):
    strategy: str
    candidate_multiplier: int
    min_score: float
    lexical_weight: float
    mmr_lambda: float


class ModelRouteStatusResponse(BaseModel):
    name: str
    provider: str
    model: Optional[str] = None
    configured: bool
    circuit_state: str


class ModelStatusResponse(BaseModel):
    gateway: str
    remote_enabled: bool
    model: Optional[str] = None
    fallback: str = "none"
    routes: List[ModelRouteStatusResponse] = Field(default_factory=list)


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
