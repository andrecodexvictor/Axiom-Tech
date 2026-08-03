from app.agents.state import AgentState

class SupervisorAgent:
    """
    Supervisor Agent that inspects incoming user queries, classifies domain intent,
    and routes execution to specialist agents.
    """

    @staticmethod
    def classify_and_route(state: AgentState) -> AgentState:
        q = state["question"].lower()

        # Keywords domain mapping
        if any(term in q for term in ["home office", "benefício", "benefit", "vr", "va", "onboarding", "slack", "comunicação", "communication", "rh", "hr"]):
            domain = "rh"
            agent = "doc_agent"
        elif any(term in q for term in ["termo", "lgpd", "privacidade", "privacy", "nda", "jurídico", "legal", "mfa", "senha"]):
            domain = "juridico"
            agent = "legal_agent"
        elif any(term in q for term in ["repo", "github", "gitlab", "código", "code", "repositório", "service map"]):
            domain = "repo"
            agent = "repo_agent"
        elif any(term in q for term in ["web", "external", "externo", "framework", "library", "pesquisa"]):
            domain = "web"
            agent = "web_agent"
        else:
            # Default to engineering for incidents, backend, frontend, microservices, architecture
            domain = "engenharia"
            agent = "engineering_agent"

        state["classified_domain"] = domain
        state["next_agent"] = agent
        state["messages"].append({"role": "supervisor", "content": f"Routed query to {agent} (Domain: {domain})"})
        return state
