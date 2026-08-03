import sys
import argparse
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.ingestion.loader import DocumentLoader
from app.ingestion.chunker import DocumentChunker
from app.vectorstore.pinecone_client import vector_store
from app.graph import axiom_graph

def initialize_knowledge_base():
    """
    Ingests all internal multi-format documents from documents/ and indexes vector embeddings.
    """
    print(f"[Ingestion] Loading internal documents from: {settings.DOCUMENTS_DIR}")
    raw_docs = DocumentLoader.load_directory(settings.DOCUMENTS_DIR)
    print(f"[Ingestion] Extracted {len(raw_docs)} document files.")

    chunker = DocumentChunker()
    chunks = chunker.split_documents(raw_docs)
    print(f"[Ingestion] Created {len(chunks)} text chunks.")

    count = vector_store.index_documents(chunks)
    print(f"[Ingestion] Successfully indexed {count} document chunks into VectorStore.")

def run_cli():
    print("=" * 65)
    print("      AXIOM TECH CORPORATE AI AGENT - V1 COMMAND LINE INTERFACE")
    print("=" * 65)
    
    initialize_knowledge_base()

    print("\nSystem ready! Type your question below (or 'exit' to quit):\n")
    while True:
        try:
            user_input = input("\n[Employee Question]: ").strip()
            if not user_input or user_input.lower() in ["exit", "quit"]:
                print("Goodbye!")
                break
            
            result = axiom_graph.run(user_input)

            print("\n" + "-" * 50)
            print(f"Domain: {result['classified_domain'].upper()} | Agent: {result['next_agent']}")
            print("-" * 50)
            print(result["final_answer"])
            if result["sources"]:
                print("\nSources Consulted:")
                for src in result["sources"]:
                    print(f" - {src}")
            print("-" * 50)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[Error] Execution failed: {e}")

def run_streamlit():
    import streamlit as st

    st.set_page_config(
        page_title="Axiom Tech Corporate AI Agent",
        page_icon="🤖",
        layout="wide"
    )

    # Custom styling
    st.markdown("""
        <style>
            .main-header { font-size: 2.2rem; color: #1E88E5; font-weight: bold; margin-bottom: 0px; }
            .sub-header { font-size: 1.1rem; color: #555555; margin-bottom: 20px; }
            .source-badge { background-color: #E3F2FD; color: #0D47A1; padding: 4px 8px; border-radius: 4px; font-size: 0.85rem; }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="main-header">Axiom Tech Corporate AI Agent</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Agentic RAG Knowledge Base — HR, Legal, Engineering & Operations</div>', unsafe_allow_html=True)

    # Sidebar initialization
    with st.sidebar:
        st.header("⚙️ Configuration & Indexing")
        if st.button("🔄 Ingest Internal Documents", use_container_width=True):
            with st.spinner("Ingesting multi-format internal documents..."):
                initialize_knowledge_base()
                st.success("Internal knowledge base successfully updated!")

        st.divider()
        st.markdown("**System Architecture**: Multi-Agent LangGraph")
        st.markdown("**LLM Motor**: NVIDIA NIM API")
        st.markdown("**Vector Store**: Pinecone Vector DB")
        st.markdown("**Anti-Hallucination**: Grounded RAG + Grade/Rewrite")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
        # Pre-initialize knowledge base on first load
        initialize_knowledge_base()

    # Display prior conversation
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # User chat input
    if prompt := st.chat_input("Ask a question about policies, incidents, backend guidelines, LGPD..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Consulting domain specialist agents..."):
                res = axiom_graph.run(prompt)
                
                answer_text = f"**[{res['classified_domain'].upper()} DOMAIN | AGENT: {res['next_agent']}]**\n\n" + res["final_answer"]
                if res["sources"]:
                    answer_text += "\n\n**Sources Consulted:**\n" + "\n".join([f"- `{src}`" for src in res["sources"]])

                st.markdown(answer_text)
                st.session_state.messages.append({"role": "assistant", "content": answer_text})

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Axiom Tech Corporate AI Agent Launcher")
    parser.add_argument("--cli", action="store_true", help="Run in Command Line Interface mode")
    args = parser.parse_args()

    if args.cli:
        run_cli()
    else:
        # Check if running via Streamlit
        if "streamlit" in sys.modules:
            run_streamlit()
        else:
            run_cli()
