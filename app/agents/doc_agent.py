from app.agents.state import AgentState
from app.vectorstore.pinecone_client import vector_store

class DocAgent:
    """
    Documentation RAG Agent focusing on HR, Onboarding, Benefits, and Internal Communications.
    """

    @staticmethod
    def process(state: AgentState) -> AgentState:
        q = state["question"]
        results = vector_store.similarity_search(query=q, domain_filter="rh", top_k=4)
        
        state["retrieved_docs"] = results
        state["sources"] = list(set([doc["metadata"]["source"] for doc in results]))

        if results:
            context_str = "\n\n".join([f"Source ({doc['metadata']['source']}):\n{doc['content']}" for doc in results])
            state["final_answer"] = f"Based on internal HR & Operational documentation:\n\n{context_str}"
        else:
            state["final_answer"] = "No direct internal HR documentation found matching your query."

        return state
