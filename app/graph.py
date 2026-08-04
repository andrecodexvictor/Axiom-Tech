"""The V3 grounded RAG workflow implemented as a LangGraph StateGraph."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.agents.state import AgentState, GraphTraceEvent
from app.agents.web_research import WebResearchAgent
from app.llm_client import NvidiaGateway
from app.vectorstore.port import RetrievedChunk, VectorStorePort

try:  # The package is a required production dependency; fallback keeps legacy CLI usable during bootstrap.
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when dependencies were not installed yet
    END = "__end__"
    START = "__start__"
    StateGraph = None  # type: ignore
    LANGGRAPH_AVAILABLE = False


MAX_REWRITES = 2
SUPPORTED_DOMAINS = {"rh", "juridico", "engenharia", "api_spec", "web"}


class AxiomAgentGraph:
    """Supervisor → retrieval/specialist → grade → rewrite/synthesize/fallback.

    The graph is deliberately deterministic at its control points.  A cloud model
    may improve prose in the synthesis node, but it cannot route around grading,
    bypass evidence, or create citations.
    """

    def __init__(
        self,
        vector_store: VectorStorePort,
        model_gateway: NvidiaGateway,
        web_research_agent: Optional[WebResearchAgent] = None,
    ) -> None:
        self.vector_store = vector_store
        self.model_gateway = model_gateway
        self.web_research_agent = web_research_agent or WebResearchAgent(model_gateway.configuration)
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        if not LANGGRAPH_AVAILABLE:
            return _BootstrapGraph(self)
        workflow = StateGraph(AgentState)
        workflow.add_node("supervisor", self._supervisor)
        workflow.add_node("web_research", self._web_research)
        workflow.add_node("retrieval", self._retrieval)
        workflow.add_node("specialist", self._specialist)
        workflow.add_node("grade", self._grade)
        workflow.add_node("rewrite", self._rewrite)
        workflow.add_node("synthesize", self._synthesize)
        workflow.add_node("fallback", self._fallback)
        workflow.add_edge(START, "supervisor")
        workflow.add_conditional_edges(
            "supervisor",
            self._after_supervisor,
            {"web": "web_research", "internal": "retrieval"},
        )
        workflow.add_edge("web_research", END)
        workflow.add_edge("retrieval", "specialist")
        workflow.add_edge("specialist", "grade")
        workflow.add_conditional_edges(
            "grade",
            self._after_grade,
            {"rewrite": "rewrite", "synthesize": "synthesize", "fallback": "fallback"},
        )
        workflow.add_edge("rewrite", "retrieval")
        workflow.add_edge("synthesize", END)
        workflow.add_edge("fallback", END)
        return workflow.compile()

    def run(
        self, user_question: str, domain: Optional[str] = None, top_k: int = 4
    ) -> Dict[str, Any]:
        question = user_question.strip()
        if not question:
            raise ValueError("question must not be empty")
        initial: AgentState = {
            "question": question,
            "requested_domain": domain if domain in SUPPORTED_DOMAINS else None,
            "active_question": question,
            "retrieved_docs": [],
            "rewrite_count": 0,
            "trace": [],
            "sources": [],
            "citations": [],
            "messages": [],
            # StateGraph carries the requested limit as ordinary state; it is not
            # exposed as part of the public answer contract.
            "top_k": max(1, min(int(top_k), 10)),
        }
        result = dict(self.graph.invoke(initial))
        # Existing CLI callers used these V1 names.
        result.setdefault("classified_domain", result.get("domain", "engenharia"))
        result.setdefault("next_agent", result.get("specialist", "engineering"))
        result.setdefault("final_answer", result.get("answer", ""))
        result.setdefault("sources", [citation["source"] for citation in result.get("citations", [])])
        return result

    def _supervisor(self, state: AgentState) -> Dict[str, Any]:
        domain = state.get("requested_domain") or self._classify(state["question"])
        specialist = {
            "rh": "hr_policy",
            "juridico": "legal_compliance",
            "api_spec": "repository_api",
            "engenharia": "engineering_operations",
            "web": "web_research",
        }[domain]
        return {
            "domain": domain,
            "classified_domain": domain,
            "specialist": specialist,
            "next_agent": specialist,
            "trace": self._trace(state, "supervisor", "routed", "Routed to {0}".format(specialist)),
        }

    @staticmethod
    def _after_supervisor(state: AgentState) -> str:
        return "web" if state.get("domain") == "web" else "internal"

    def _web_research(self, state: AgentState) -> Dict[str, Any]:
        result = self.web_research_agent.research(state["question"], limit=int(state.get("top_k", 4)))
        citations = list(result.citations)
        return {
            "answer": result.answer,
            "final_answer": result.answer,
            "grounded": result.grounded,
            "citations": citations,
            "sources": list(dict.fromkeys(citation["source"] for citation in citations)),
            "trace": list(state.get("trace", [])) + list(result.trace),
        }

    def _retrieval(self, state: AgentState) -> Dict[str, Any]:
        query = state["active_question"]
        limit = int(state.get("top_k", 4))
        domain = state.get("domain")
        documents = self.vector_store.search(query=query, domain=domain, limit=limit)
        return {
            "retrieved_docs": documents,
            "trace": self._trace(
                state,
                "retrieval",
                "searched",
                "Retrieved {0} {1} candidate chunk(s)".format(len(documents), domain or "all-domain"),
            ),
        }

    def _specialist(self, state: AgentState) -> Dict[str, Any]:
        documents = list(state.get("retrieved_docs", []))
        # If a classifier's domain is too narrow, a cross-domain pass is safe: the
        # grader still requires textual evidence and citations retain true domain.
        if not documents and state.get("domain"):
            documents = self.vector_store.search(
                query=state["active_question"], domain=None, limit=int(state.get("top_k", 4))
            )
            detail = "No domain evidence; performed a cross-domain retrieval"
        else:
            detail = "Specialist evaluated {0} retrieved chunk(s)".format(len(documents))
        citations = [item.citation() for item in documents]
        sources = list(dict.fromkeys(citation["source"] for citation in citations))
        return {
            "retrieved_docs": documents,
            "citations": citations,
            "sources": sources,
            "trace": self._trace(state, "specialist", "evaluated", detail),
        }

    def _grade(self, state: AgentState) -> Dict[str, Any]:
        documents = list(state.get("retrieved_docs", []))
        coverage = self._evidence_coverage(state["question"], documents)
        passed = bool(documents) and coverage >= 0.15
        status = "passed" if passed else "rewrite"
        detail = "Evidence coverage {0:.2f}; {1}".format(
            coverage, "grounded synthesis allowed" if passed else "insufficient evidence"
        )
        return {
            "grade_status": status,
            "trace": self._trace(state, "grade", status, detail),
        }

    def _after_grade(self, state: AgentState) -> str:
        if state.get("grade_status") == "passed":
            return "synthesize"
        if int(state.get("rewrite_count", 0)) < MAX_REWRITES:
            return "rewrite"
        return "fallback"

    def _rewrite(self, state: AgentState) -> Dict[str, Any]:
        attempt = int(state.get("rewrite_count", 0)) + 1
        rewrite = self._rewrite_query(state["question"], attempt)
        return {
            "active_question": rewrite,
            "rewrite_count": attempt,
            "trace": self._trace(
                state, "rewrite", "rewritten", "Prepared bounded retrieval rewrite {0}/{1}".format(attempt, MAX_REWRITES)
            ),
        }

    def _synthesize(self, state: AgentState) -> Dict[str, Any]:
        evidence = list(state.get("retrieved_docs", []))
        synthesis = self.model_gateway.synthesize(state["question"], evidence)
        return {
            "answer": synthesis.answer,
            "final_answer": synthesis.answer,
            "grounded": True,
            "synthesis_mode": synthesis.mode,
            "trace": self._trace(
                state, "synthesize", synthesis.mode, "Produced an answer from graded internal evidence"
            ),
        }

    def _fallback(self, state: AgentState) -> Dict[str, Any]:
        if NvidiaGateway._is_portuguese(state["question"]):
            answer = (
                "Não consigo fundamentar uma resposta na documentação interna indexada. "
                "Tente informar a política, o sistema, o documento ou um tópico mais específico."
            )
        else:
            answer = (
                "I can’t substantiate an answer from the indexed internal documentation. "
                "Try naming a policy, system, document, or a more specific topic."
            )
        return {
            "answer": answer,
            "final_answer": answer,
            "grounded": False,
            "citations": [],
            "sources": [],
            "trace": self._trace(
                state,
                "fallback",
                "unsupported",
                "No adequate internal evidence after {0} rewrite(s)".format(state.get("rewrite_count", 0)),
            ),
        }

    @staticmethod
    def _classify(question: str) -> str:
        value = question.lower()
        rules = (
            ("web", ("search the web", "web research", "internet research", "online research", "external research")),
            ("juridico", ("lgpd", "privacidade", "privacy", "termo", "terms", "legal", "compliance", "dados pessoais")),
            ("rh", ("home office", "benefício", "beneficio", "onboarding", "reembolso", "expense", "férias", "ferias", "rh")),
            ("api_spec", ("endpoint", "api", "repo", "github", "openapi", "swagger", "repository")),
        )
        for domain, keywords in rules:
            if any(keyword in value for keyword in keywords):
                return domain
        return "engenharia"

    @staticmethod
    def _evidence_coverage(question: str, documents: List[RetrievedChunk]) -> float:
        stop_words = {
            "a", "an", "and", "as", "at", "como", "da", "de", "do", "e", "for", "how", "is", "o", "of", "on", "or", "os", "para", "qual", "que", "the", "to", "um", "uma", "what", "with",
        }
        terms = {
            word
            for word in re.findall(r"[\wÀ-ÿ][\wÀ-ÿ._/-]*", question.lower(), flags=re.UNICODE)
            if len(word) > 2 and word not in stop_words
        }
        if not documents:
            return 0.0
        content = " ".join(document.content.lower() for document in documents)
        matching = sum(1 for term in terms if term in content)
        lexical = matching / max(1, len(terms))
        # Retrieval distance narrows candidates, but cannot on its own establish a
        # claim: deterministic vectors (and cloud vectors) can surface loosely
        # related text.  Grading therefore requires lexical evidence from the
        # actual retrieved content before synthesis is permitted.
        return lexical

    @staticmethod
    def _rewrite_query(question: str, attempt: int) -> str:
        words = re.findall(r"[\wÀ-ÿ][\wÀ-ÿ._/-]*", question, flags=re.UNICODE)
        meaningful = [word for word in words if len(word) > 2]
        base = " ".join(meaningful) or question
        suffix = "internal policy" if attempt == 1 else "procedure guideline"
        return "{0} {1}".format(base, suffix)

    @staticmethod
    def _trace(state: AgentState, node: str, event: str, details: str) -> List[GraphTraceEvent]:
        trace = list(state.get("trace", []))
        trace.append({"node": node, "event": event, "details": details})
        return trace


class _BootstrapGraph:
    """Compatibility execution only for environments where LangGraph is absent."""

    def __init__(self, owner: AxiomAgentGraph) -> None:
        self.owner = owner

    def invoke(self, initial: AgentState) -> Dict[str, Any]:  # pragma: no cover - bootstrap only
        state: Dict[str, Any] = dict(initial)
        state.update(self.owner._supervisor(state))
        if self.owner._after_supervisor(state) == "web":
            state.update(self.owner._web_research(state))
            return state
        for node in (self.owner._retrieval, self.owner._specialist):
            state.update(node(state))
        while True:
            state.update(self.owner._grade(state))
            decision = self.owner._after_grade(state)
            if decision == "synthesize":
                state.update(self.owner._synthesize(state))
                return state
            if decision == "fallback":
                state.update(self.owner._fallback(state))
                return state
            state.update(self.owner._rewrite(state))
            state.update(self.owner._retrieval(state))
            state.update(self.owner._specialist(state))


# The former module exported a singleton.  The API deliberately builds an injected
# graph; retaining no eagerly configured singleton avoids accidental Chroma writes
# at import time.
