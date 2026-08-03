from typing import Dict, Any
from app.agents.state import AgentState
from app.agents.supervisor import SupervisorAgent
from app.agents.doc_agent import DocAgent
from app.agents.engineering_agent import EngineeringAgent
from app.agents.legal_agent import LegalAgent
from app.agents.repo_agent import RepoAgent
from app.agents.web_research import WebResearchAgent
from app.agents.grader import DocumentGrader

class AxiomAgentGraph:
    """
    LangGraph Multi-Agent Workflow Engine for Axiom Tech.
    Orchestrates Supervisor -> Specialist Agent -> Grader / Rewrite -> Synthesizer.
    """

    def __init__(self):
        self.supervisor = SupervisorAgent()
        self.doc_agent = DocAgent()
        self.eng_agent = EngineeringAgent()
        self.legal_agent = LegalAgent()
        self.repo_agent = RepoAgent()
        self.web_agent = WebResearchAgent()
        self.grader = DocumentGrader()

    def run(self, user_question: str) -> Dict[str, Any]:
        state: AgentState = {
            "question": user_question,
            "classified_domain": "",
            "next_agent": "",
            "retrieved_docs": [],
            "grade_status": "",
            "rewrite_count": 0,
            "final_answer": "",
            "sources": [],
            "messages": []
        }

        # Step 1: Supervisor Classification & Routing
        state = self.supervisor.classify_and_route(state)
        next_agent = state["next_agent"]

        # Step 2: Route to Specialist Agent
        if next_agent == "doc_agent":
            state = self.doc_agent.process(state)
        elif next_agent == "legal_agent":
            state = self.legal_agent.process(state)
        elif next_agent == "repo_agent":
            state = self.repo_agent.process(state)
        elif next_agent == "web_agent":
            state = self.web_agent.process(state)
        else:
            state = self.eng_agent.process(state)

        # Step 3: Grade Documents & Grounding Check
        state = self.grader.grade_and_rewrite(state)

        # Step 4: Handle Retry / Rewrite if needed
        if state["grade_status"] == "REWRITE":
            if next_agent == "doc_agent":
                state = self.doc_agent.process(state)
            elif next_agent == "legal_agent":
                state = self.legal_agent.process(state)
            else:
                state = self.eng_agent.process(state)

        return state

axiom_graph = AxiomAgentGraph()
