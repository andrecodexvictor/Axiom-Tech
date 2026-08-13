"""The bounded grounded-retrieval workflow implemented as a LangGraph StateGraph."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from app.agents.grounding import (
    deduplicate_evidence,
    grade_evidence,
    rewrite_query,
)
from app.agents.routing import (
    SUPPORTED_DOMAINS,
    classify_domain,
    specialist_for,
    validate_requested_domain,
)
from app.agents.state import AgentState, GraphTraceEvent
from app.agents.web_research import WebResearchAgent
from app.llm_client import ModelGateway
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
MAX_GRAPH_RECURSION = 18


logger = logging.getLogger(__name__)


class AxiomAgentGraph:
    """Route → retrieve → grade → bounded reformulation → answer/refuse.

    This is an observable LangGraph workflow, not a claim that private model
    reasoning is exposed as ReAct.  Control decisions are deterministic and every
    retrieval action is bounded.  A cloud model may improve prose in synthesis,
    but it cannot route around grading, bypass evidence, or create citations.
    """

    def __init__(
        self,
        vector_store: VectorStorePort,
        model_gateway: ModelGateway,
        web_research_agent: Optional[WebResearchAgent] = None,
    ) -> None:
        self.vector_store = vector_store
        self.model_gateway = model_gateway
        self.web_research_agent = web_research_agent or WebResearchAgent(model_gateway.configuration)
        self._semantic_grounding = self._compute_semantic_grounding_allowed()
        self._langsmith_client: Any = None
        self._langsmith_unavailable = False
        self._langsmith_lock = threading.Lock()
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
        started = time.perf_counter()
        question = user_question.strip()
        if not question:
            raise ValueError("question must not be empty")
        requested_domain = validate_requested_domain(domain)
        requested_limit = max(1, min(int(top_k), 10))
        initial: AgentState = {
            "question": question,
            "requested_domain": requested_domain,
            "active_question": question,
            "retrieval_domain": requested_domain,
            "retrieved_docs": [],
            "rewrite_count": 0,
            "trace": [],
            "sources": [],
            "citations": [],
            "messages": [],
            "timings_ms": {},
            # StateGraph carries the requested limit as ordinary state; it is not
            # exposed as part of the public answer contract.
            "top_k": requested_limit,
        }
        run_config = {
            "recursion_limit": MAX_GRAPH_RECURSION,
            "run_name": "axiom-grounded-query",
            "tags": ["axiom-v3", "grounded-retrieval"],
            "metadata": self._trace_metadata(requested_domain, requested_limit),
        }
        with self._langsmith_scope():
            if LANGGRAPH_AVAILABLE:
                result = dict(self.graph.invoke(initial, config=run_config))
            else:
                result = dict(self.graph.invoke(initial))
        # Existing CLI callers used these V1 names.
        result.setdefault("classified_domain", result.get("domain", "engenharia"))
        result.setdefault("next_agent", result.get("specialist", "engineering"))
        result.setdefault("final_answer", result.get("answer", ""))
        result.setdefault("sources", [citation["source"] for citation in result.get("citations", [])])
        timings = dict(result.get("timings_ms", {}) or {})
        timings["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
        result["timings_ms"] = timings
        result["duration_ms"] = timings["total_ms"]
        return result

    def _supervisor(self, state: AgentState) -> Dict[str, Any]:
        domain = state.get("requested_domain") or classify_domain(state["question"])
        specialist = specialist_for(domain)
        return {
            "domain": domain,
            "retrieval_domain": domain,
            "classified_domain": domain,
            "specialist": specialist,
            "next_agent": specialist,
            "trace": self._trace(state, "supervisor", "routed", "Routed to {0}".format(specialist)),
        }

    @staticmethod
    def _after_supervisor(state: AgentState) -> str:
        return "web" if state.get("domain") == "web" else "internal"

    def _web_research(self, state: AgentState) -> Dict[str, Any]:
        started = time.perf_counter()
        result = self.web_research_agent.research(state["question"], limit=int(state.get("top_k", 4)))
        citations = list(result.citations)
        timings = self._timings(state)
        timings["web_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return {
            "answer": result.answer,
            "final_answer": result.answer,
            "grounded": result.grounded,
            "citations": citations,
            "sources": list(dict.fromkeys(citation["source"] for citation in citations)),
            "trace": list(state.get("trace", [])) + list(result.trace),
            "timings_ms": timings,
        }

    def _retrieval(self, state: AgentState) -> Dict[str, Any]:
        started = time.perf_counter()
        query = state["active_question"]
        limit = int(state.get("top_k", 4))
        domain = state.get("retrieval_domain", state.get("domain"))
        documents = self.vector_store.search(query=query, domain=domain, limit=limit)
        scope = domain or "all-domains"
        step = int(state.get("rewrite_count", 0)) + 1
        timings = self._timings(state)
        timings["retrieval_ms"] = round(
            float(timings.get("retrieval_ms", 0.0)) + (time.perf_counter() - started) * 1000,
            1,
        )
        return {
            "retrieved_docs": documents,
            "trace": self._trace(
                state,
                "retrieval",
                "searched",
                "Retrieval step {0}/{1}: accepted {2} candidate chunk(s) in {3}".format(
                    step, MAX_REWRITES + 1, len(documents), scope
                ),
            ),
            "timings_ms": timings,
        }

    def _specialist(self, state: AgentState) -> Dict[str, Any]:
        documents = deduplicate_evidence(
            state.get("retrieved_docs", []), limit=int(state.get("top_k", 4))
        )
        detail = "Specialist accepted {0} unique evidence chunk(s)".format(len(documents))
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
        grade = grade_evidence(
            state["question"],
            documents,
            allow_semantic_only=self._semantic_grounding_allowed(),
        )
        status = "passed" if grade.passed else "rewrite"
        detail = "Coverage {0:.2f}, best relevance {1:.2f}; {2}".format(
            grade.lexical_coverage,
            grade.best_relevance_score,
            "grounded synthesis allowed" if grade.passed else "insufficient evidence",
        )
        return {
            "grade_status": status,
            "evidence_coverage": grade.lexical_coverage,
            "best_relevance_score": grade.best_relevance_score,
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
        domain = str(state.get("domain", "engenharia"))
        rewrite = rewrite_query(state["question"], attempt, domain)
        # An inferred domain may be wrong.  The final bounded retrieval action can
        # widen scope, but an explicitly requested domain is always respected.
        retrieval_domain = domain
        if attempt == MAX_REWRITES and state.get("requested_domain") is None:
            retrieval_domain = None
        scope = retrieval_domain or "all-domains"
        return {
            "active_question": rewrite,
            "rewrite_count": attempt,
            "retrieval_domain": retrieval_domain,
            "trace": self._trace(
                state,
                "rewrite",
                "rewritten",
                "Prepared retrieval reformulation {0}/{1}; next scope {2}".format(
                    attempt, MAX_REWRITES, scope
                ),
            ),
        }

    def _synthesize(self, state: AgentState) -> Dict[str, Any]:
        started = time.perf_counter()
        evidence = list(state.get("retrieved_docs", []))
        synthesis = self.model_gateway.synthesize(state["question"], evidence)
        timings = self._timings(state)
        timings["synthesis_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return {
            "answer": synthesis.answer,
            "final_answer": synthesis.answer,
            "grounded": True,
            "synthesis_mode": synthesis.mode,
            "trace": self._trace(
                state, "synthesize", synthesis.mode, "Produced an answer from graded internal evidence"
            ),
            "timings_ms": timings,
        }

    def _fallback(self, state: AgentState) -> Dict[str, Any]:
        if ModelGateway._is_portuguese(state["question"]):
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
        return classify_domain(question)

    @staticmethod
    def _evidence_coverage(question: str, documents: List[RetrievedChunk]) -> float:
        return grade_evidence(question, documents).lexical_coverage

    @staticmethod
    def _rewrite_query(question: str, attempt: int) -> str:
        return rewrite_query(question, attempt, "engenharia")

    @staticmethod
    def _trace(state: AgentState, node: str, event: str, details: str) -> List[GraphTraceEvent]:
        trace = list(state.get("trace", []))
        safe_details = " ".join(str(details).split())[:320]
        trace.append({"node": node, "event": event, "details": safe_details})
        return trace

    def _trace_metadata(self, requested_domain: Optional[str], top_k: int) -> Dict[str, Any]:
        status = self.vector_store.status()
        embedding = status.get("embedding", {})
        return {
            "workflow": "grounded-retrieval-v1",
            "requested_domain": requested_domain or "automatic",
            "top_k": top_k,
            "vector_backend": str(status.get("backend", "unknown")),
            "embedding_fingerprint": str(embedding.get("fingerprint", "")),
        }

    def _semantic_grounding_allowed(self) -> bool:
        return self._semantic_grounding

    def _compute_semantic_grounding_allowed(self) -> bool:
        embedding = dict(self.vector_store.status().get("embedding", {}) or {})
        return bool(
            embedding.get("configured")
            and embedding.get("mode") == "remote"
            and embedding.get("provider") not in {"", "deterministic", "disabled"}
        )

    @staticmethod
    def _timings(state: AgentState) -> Dict[str, float]:
        return dict(state.get("timings_ms", {}) or {})

    @contextmanager
    def _langsmith_scope(self):
        configuration = self.model_gateway.configuration
        if not bool(getattr(configuration, "langsmith_enabled", False)):
            yield
            return
        try:
            from langsmith import Client, tracing_context

            client_options: Dict[str, Any] = {
                "api_key": configuration.langsmith_api_key,
                "api_url": configuration.langsmith_endpoint,
            }
            if configuration.langsmith_workspace_id:
                client_options["workspace_id"] = configuration.langsmith_workspace_id
            if configuration.langsmith_hide_inputs:
                client_options["hide_inputs"] = lambda _inputs: {}
            if configuration.langsmith_hide_outputs:
                client_options["hide_outputs"] = lambda _outputs: {}
            with self._langsmith_lock:
                unavailable = self._langsmith_unavailable
                if not unavailable:
                    if self._langsmith_client is None:
                        self._langsmith_client = Client(**client_options)
                    client = self._langsmith_client
            if unavailable:
                yield
                return
            context = tracing_context(
                enabled=True,
                client=client,
                project_name=configuration.langsmith_project,
            )
            stack = ExitStack()
            stack.enter_context(context)
        except Exception as exc:
            self._langsmith_unavailable = True
            logger.warning("LangSmith tracing unavailable (%s)", type(exc).__name__)
            yield
            return
        with stack:
            yield


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
