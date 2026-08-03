# Rule: Governance with dotarchitecture, dotcontext, and dotstack

When the user mentions or requests `dotarchitecture`, `dotcontext`, or `dotstack` (or `.architecture`, `.context`, `.stack` files):

1. **dotarchitecture**:
   - Manages and generates architectural specifications, agent graph flows, multi-agent designs, and system patterns.
   - Preserves system design, component boundaries, and agent routing logic in `.architecture`, `.architecture.md`, or `ARCHITECTURE.md`.

2. **dotcontext**:
   - Manages business context, organizational domains, persona rules, domain knowledge, anti-hallucination policies, and session memory.
   - Preserves domain context in `.context`, `.context.md`, or `AGENTS.md`.

3. **dotstack**:
   - Manages technology stack selections, dependencies, environment constraints, and deployment targets (NVIDIA NIM/API, LangGraph, Pinecone, Streamlit, OCI).
   - Preserves technical stack specifications in `.stack`, `.stack.md`, or `STACK.md`.

4. **Execution Protocol**:
   - Always keep `.architecture`, `.context`, and `.stack` updated when project structure, domain requirements, or technology stack change.
   - When generating or managing codebase files, write in clean, professional English to optimize token usage and maintain standard enterprise codebase practices.
