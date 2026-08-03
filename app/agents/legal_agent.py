from app.agents.state import AgentState
from app.vectorstore.pinecone_client import vector_store
from app.llm_client import nvidia_client

class LegalAgent:
    """
    Legal & Compliance Agent powered by MiniMax M3 (minimaxai/minimax-m3).
    """

    @staticmethod
    def process(state: AgentState) -> AgentState:
        q = state["question"]
        results = vector_store.similarity_search(query=q, domain_filter="juridico", top_k=4)

        state["retrieved_docs"] = results
        state["sources"] = list(set([doc["metadata"]["source"] for doc in results]))

        if results:
            context_str = "\n\n".join([f"Source ({doc['metadata']['source']}):\n{doc['content']}" for doc in results])
            prompt = f"Using MiniMax M3, answer the legal/compliance query strictly based on context:\n\nContext:\n{context_str}\n\nQuestion: {q}"
            state["final_answer"] = nvidia_client.invoke_minimax(prompt)
        else:
            state["final_answer"] = "No direct legal & compliance documents found matching your query."

        return state
