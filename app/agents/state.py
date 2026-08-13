"""Typed state carried through the V3 LangGraph workflow."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class GraphTraceEvent(TypedDict):
    node: str
    event: str
    details: str


class AgentState(TypedDict, total=False):
    question: str
    requested_domain: Optional[str]
    active_question: str
    top_k: int
    retrieval_domain: Optional[str]
    domain: str
    classified_domain: str  # Retained for V1 CLI compatibility.
    specialist: str
    next_agent: str  # Retained for V1 CLI compatibility.
    retrieved_docs: List[Any]
    grade_status: str
    evidence_coverage: float
    best_relevance_score: float
    rewrite_count: int
    final_answer: str
    sources: List[str]
    citations: List[Dict[str, Any]]
    trace: List[GraphTraceEvent]
    messages: List[Dict[str, str]]
    grounded: bool
    synthesis_mode: str
