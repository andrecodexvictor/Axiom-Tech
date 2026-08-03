from app.agents.state import AgentState
from app.vectorstore.pinecone_client import vector_store

class EngineeringAgent:
    """
    Engineering & Incident Specialist Agent focusing on microservices architecture,
    backend/frontend guidelines, and SEV-1/2 incident response procedures.
    """

    @staticmethod
    def process(state: AgentState) -> AgentState:
        q = state["question"]
        results = vector_store.similarity_search(query=q, domain_filter="engenharia", top_k=4)

        state["retrieved_docs"] = results
        state["sources"] = list(set([doc["metadata"]["source"] for doc in results]))

        if results:
            context_str = "\n\n".join([f"Source ({doc['metadata']['source']}):\n{doc['content']}" for doc in results])
            state["final_answer"] = f"Based on Engineering & Incident Documentation:\n\n{context_str}"
        else:
            state["final_answer"] = "No direct engineering guidelines found matching your query."

        return state
