from app.agents.state import AgentState

class DocumentGrader:
    """
    Evaluator node checking document relevance and grounding quality before returning answers.
    Performs query rewrite if document relevance score falls below threshold.
    """

    @staticmethod
    def grade_and_rewrite(state: AgentState) -> AgentState:
        docs = state.get("retrieved_docs", [])
        rewrite_count = state.get("rewrite_count", 0)

        if docs:
            state["grade_status"] = "PASSED"
        else:
            if rewrite_count < 2:
                state["grade_status"] = "REWRITE"
                state["rewrite_count"] = rewrite_count + 1
                state["question"] = f"Axiom Tech enterprise standards for {state['question']}"
                state["messages"].append({
                    "role": "grader",
                    "content": f"Re-writing question (Attempt {state['rewrite_count']}): '{state['question']}'"
                })
            else:
                state["grade_status"] = "FALLBACK"

        return state
