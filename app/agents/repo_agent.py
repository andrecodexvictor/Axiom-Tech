from app.agents.state import AgentState
from app.vectorstore.pinecone_client import vector_store

class RepoAgent:
    """
    RepoAgent focusing on internal repository structures, code modules, and API specifications.
    """

    @staticmethod
    def process(state: AgentState) -> AgentState:
        q = state["question"]
        results = vector_store.similarity_search(query=q, domain_filter="api_spec", top_k=4)

        if not results:
            results = vector_store.similarity_search(query=q, domain_filter="engenharia", top_k=4)

        state["retrieved_docs"] = results
        state["sources"] = list(set([doc["metadata"]["source"] for doc in results]))

        if results:
            context_str = "\n\n".join([f"Source ({doc['metadata']['source']}):\n{doc['content']}" for doc in results])
            state["final_answer"] = f"Based on Internal Repository & API Specifications:\n\n{context_str}"
        else:
            state["final_answer"] = "No matching internal repository specifications found."

        return state
