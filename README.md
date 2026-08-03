# Axiom Tech Corporate AI Agent (V1)

## Overview & Background (Minimundo)
**Axiom Tech** is a technology enterprise developing digital platforms, enterprise automation services, and AI solutions. This project implements V1 of the Axiom Tech Corporate AI Agent: a centralized conversational knowledge assistant accessible to all employees.

The agent answers natural language questions regarding internal policies, incident procedures, microservice architectures, legal terms, and compliance guidelines, backed by internal documents in multiple formats (**PDF, Word, Excel, CSV, JSON, Markdown, HTML**).

---

## Technical Stack & Architecture

- **Governance Specifications**: Built using `.architecture` (DotArchitecture), `.context` (DotContext), and `.stack` (DotStack) standards.
- **LLM Reasoning Engine**: NVIDIA NIM / API (`meta/llama-3.1-70b-instruct`).
- **Multi-Agent Orchestration**: **LangGraph** workflow engine (Supervisor -> Specialist Agents -> Grade/Rewrite -> Synthesizer).
- **Vector Store**: **Pinecone Vector DB** (with automatic local index fallback for offline dev).
- **User Interface**: Interactive **Streamlit** Web Application & CLI mode.
- **Cloud Infrastructure**: Deployable on Oracle Cloud Infrastructure (OCI Compute / GenAI Containers).

---

## Multi-Agent Architecture

```
                       ┌─────────────────────────┐
                       │    Supervisor Agent     │
                       └────────────┬────────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           ▼                        ▼                        ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│  Doc RAG Agent      │  │  Engineering Agent  │  │  Legal Agent        │
│  (HR / Comms)       │  │  (Architecture/SEVs)│  │  (LGPD / Terms)     │
└──────────┬──────────┘  └──────────┬──────────┘  └──────────┬──────────┘
           │                        │                        │
           └────────────────────────┼────────────────────────┘
                                    ▼
                       ┌─────────────────────────┐
                       │   Grade & Rewrite Node  │
                       └────────────┬────────────┘
                                    ▼
                       ┌─────────────────────────┐
                       │  Synthesizer with Source│
                       │       Citations         │
                       └─────────────────────────┘
```

---

## Folder Structure

```
Axiom Tech/
├── .architecture               # DotArchitecture specification
├── .context                    # DotContext domain memory specification
├── .stack                      # DotStack technical stack specification
├── .agents/rules/              # Antigravity custom governance rules
├── .env.example                # Template for API keys (NVIDIA, Pinecone)
├── README.md                   # Complete documentation
├── requirements.txt            # Python dependencies
├── documentos/                 # Synthetic corporate documents
│   ├── engenharia/             # Guidelines, Microservices map, SEV Incident manual
│   ├── juridico/               # Privacy policy (LGPD), Internal Terms of Use
│   ├── rh/                     # Benefits CSV, Onboarding guide, Internal Comms
│   └── api_spec/               # Internal API specification JSON
└── app/                        # Main application code
    ├── config.py               # Settings and environment loader
    ├── ingestion/              # Multi-format document loader and chunker
    ├── vectorstore/            # Pinecone connector & vector index
    ├── agents/                 # LangGraph specialist agent nodes
    ├── graph.py                # LangGraph flow compilation
    └── main.py                 # Streamlit UI & CLI runner
```

---

## How to Run

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables (Optional for Pinecone/NVIDIA NIM)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### 3. Run Command Line Interface (CLI) Mode
```bash
python app/main.py --cli
```

### 4. Run Streamlit Web Application
```bash
streamlit run app/main.py
```

---

## Verification & Sample Queries

- **HR & Policies**: *"Qual é a política de home office e o valor do vale refeição?"*
- **Incident Response**: *"Como proceder em incidentes de severidade SEV-1?"*
- **Engineering Architecture**: *"Como funciona a arquitetura de microsserviços e observability?"*
- **Legal & Compliance**: *"Quais são os principais direitos dos titulares na política de LGPD?"*
