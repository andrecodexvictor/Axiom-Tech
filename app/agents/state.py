from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    question: str
    classified_domain: str
    next_agent: str
    retrieved_docs: List[Dict[str, Any]]
    grade_status: str
    rewrite_count: int
    final_answer: str
    sources: List[str]
    messages: List[Dict[str, str]]
