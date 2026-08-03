from app.agents.state import AgentState
from app.vectorstore.pinecone_client import vector_store

class LegalAgent:
    """
    Legal & Compliance Agent focusing on LGPD privacy laws, internal terms of use,
    data security policies, and NDA compliance.
    """

    @staticmethod
    def process(state: AgentState) -> AgentState:
        q = state["question"]
        results = vector_store.similarity_search(query=q, domain_filter="juridico", top_k=4)

        state["retrieved_docs"] = results
        state["sources"] = list(set([doc["metadata"]["source"] for doc in results]))

        if results:
            context_str = "\n\n".join([f"Source ({doc['metadata']['source']}):\n{doc['content']}" for doc in results])
            state["final_answer"] = f"Based on Legal & Compliance Policies:\n\n{context_str}"
        else:
            state["final_answer"] = "No direct legal & compliance documents found matching your query."

        return state
