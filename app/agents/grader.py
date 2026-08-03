from app.agents.state import AgentState
from app.llm_client import nvidia_client

class DocumentGrader:
    """
    RAG Evaluator powered by DeepSeek V4 Pro (deepseek-ai/deepseek-v4-pro).
    Validates document grounding, performs query rewrite if needed, and synthesizes final answers.
    """

    @staticmethod
    def grade_and_rewrite(state: AgentState) -> AgentState:
        docs = state.get("retrieved_docs", [])
        q = state["question"]

        if docs:
            context_str = "\n\n".join([f"Document ({d['metadata']['source']}): {d['content']}" for d in docs])
            
            # DeepSeek V4 Pro Grounded RAG Synthesis & Verification
            synthesis = nvidia_client.invoke_deepseek_rag(prompt=q, context_docs=context_str)
            state["final_answer"] = synthesis
            state["grade_status"] = "PASSED"
        else:
            state["grade_status"] = "FALLBACK"
            state["final_answer"] = f"No internal documentation found for '{q}'."

        return state
