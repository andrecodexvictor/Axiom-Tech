from app.agents.state import AgentState
from app.llm_client import nvidia_client

class SupervisorAgent:
    """
    Supervisor Agent powered by Moonshot AI Kimi K2.6 (moonshotai/kimi-k2.6).
    Performs multi-step reasoning and classifies user intent into domain specialists.
    """

    @staticmethod
    def classify_and_route(state: AgentState) -> AgentState:
        q = state["question"]
        system_prompt = (
            "You are Axiom Tech's Supervisor Agent powered by Kimi K2.6. "
            "Classify the input question into exactly ONE domain: 'rh', 'juridico', 'repo', 'web', or 'engenharia'. "
            "Respond ONLY with the single word domain code."
        )

        try:
            domain_response = nvidia_client.invoke_kimi(q, system_prompt).strip().lower()
            if "rh" in domain_response:
                domain, agent = "rh", "doc_agent"
            elif "juridico" in domain_response or "legal" in domain_response:
                domain, agent = "juridico", "legal_agent"
            elif "repo" in domain_response or "code" in domain_response:
                domain, agent = "repo", "repo_agent"
            elif "web" in domain_response:
                domain, agent = "web", "web_agent"
            else:
                domain, agent = "engenharia", "engineering_agent"
        except Exception:
            # Fallback keyword logic
            q_lower = q.lower()
            if any(t in q_lower for t in ["home office", "benefício", "vr", "va", "onboarding"]):
                domain, agent = "rh", "doc_agent"
            elif any(t in q_lower for t in ["lgpd", "privacidade", "termo", "nda"]):
                domain, agent = "juridico", "legal_agent"
            elif any(t in q_lower for t in ["repo", "github", "api", "endpoint"]):
                domain, agent = "repo", "repo_agent"
            elif any(t in q_lower for t in ["web", "external"]):
                domain, agent = "web", "web_agent"
            else:
                domain, agent = "engenharia", "engineering_agent"

        state["classified_domain"] = domain
        state["next_agent"] = agent
        state["messages"].append({
            "role": "supervisor (Kimi K2.6)",
            "content": f"Routed query to '{agent}' (Domain: {domain})"
        })
        return state
