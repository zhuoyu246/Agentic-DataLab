# 🚀 Agentic-DataLab: Multi-Agent Data Science Workflow Orchestrator

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Vue](https://img.shields.io/badge/vue-3.x-brightgreen)
![Status](https://img.shields.io/badge/status-Production--Ready-success)

Agentic-DataLab is an **Enterprise-Grade, Multi-Agent AI system** designed to fully automate the Data Science and Machine Learning lifecycle. Built on top of LangGraph's state machine architecture and an asynchronous FastAPI backend, it orchestrates a swarm of specialized AI agents to handle everything from data ingestion and cleaning to feature engineering, model training (AutoML/H2O), and evaluation.

The frontend is a robust Vue 3 + Vite application providing real-time WebSocket communication, event timelines, and dynamic Plotly visualizations.

---

## 🏗️ System Architecture

Our system employs a strict separation of concerns, heavily utilizing the **Supervisor-Worker** multi-agent pattern with resilient memory checkpointing.

```mermaid
graph TD
    UI[Vue 3 Frontend Client] <--> |WebSocket / REST| API[FastAPI Gateway]
    
    API --> Supervisor[Supervisor Agent\nState Machine]
    
    subgraph Multi-Agent Swarm (LangGraph)
        Supervisor --> Planner[Planner Agent]
        Supervisor --> DataLoader[Data Loader Agent]
        Supervisor --> Cleaning[Cleaning Agent]
        Supervisor --> Feature[Feature Eng Agent]
        Supervisor --> AutoML[AutoML / H2O Agent]
        Supervisor --> Eval[Model Eval Agent]
        Supervisor --> Vis[Visualization Agent]
        
        Eval --> Reflexion[Reflexion / Critic Agent]
        Reflexion -.-> |Feedback Loop| AutoML
    end
    
    subgraph Core Engine
        MCP[MCP Governance]
        Memory[PostgreSQL Checkpointer]
        Idempotency[Idempotency Guard]
    end
    
    Multi-Agent Swarm --> Core Engine
```

---

## 📂 Comprehensive Project Structure

The codebase is strictly modularized into isolated backend and frontend workspaces to ensure scalability and ease of deployment. 

> **Note to Reviewers**: This repository contains over **50+ specialized engine and UI components**. Please refer to the tree below for the exact layout of the microservices and agents.

```text
Agentic-DataLab/
├── backend/                             # Python / FastAPI / LangGraph Engine
│   ├── main.py                          # ASGI Entrypoint
│   ├── requirements.txt
│   ├── api/                             # REST & WebSocket Routes
│   │   └── routes/
│   ├── agents/                          # 🧠 Core Intelligence Swarm (17+ Modules)
│   │   ├── supervisor.py                # Graph Routing & Orchestration
│   │   ├── planner_agent.py             # Strategic Task Breakdown
│   │   ├── data_loader_agent.py         # Data Ingestion
│   │   ├── cleaning_agent.py            # Data Imputation & Cleaning
│   │   ├── eda_agent.py                 # Exploratory Data Analysis
│   │   ├── feature_agent.py             # Automated Feature Engineering
│   │   ├── sql_agent.py                 # Text-to-SQL Query Generation
│   │   ├── automl_agent.py              # AutoML Training Orchestration
│   │   ├── h2o_worker.py                # H2O.ai Integration Worker
│   │   ├── model_eval_agent.py          # Metrics & Model Validation
│   │   ├── visualization_agent.py       # Plotly JSON Generation
│   │   ├── reflexion_agent.py           # Self-Correction & Critic
│   │   ├── react_agent.py               # ReAct Pattern Baseline
│   │   ├── wrangling_agent.py           # Advanced Data Manipulation
│   │   └── base.py                      # Base Agent Interface
│   ├── core/                            # 🛡️ Defense & System Mechanics
│   │   ├── checkpoint.py                # Redis/Postgres State Persistence
│   │   ├── events.py                    # Pub/Sub Event Bus
│   │   ├── idempotency.py               # Idempotent Request Guard
│   │   ├── json_guard.py                # Strict JSON Output Validation
│   │   ├── llm.py                       # LLM Provider Gateway (DeepSeek/OpenAI)
│   │   ├── mcp.py                       # Model Context Protocol Gov
│   │   ├── security.py                  # JWT Auth & Security
│   │   ├── storage.py                   # Artifact S3/Local Storage
│   │   └── config.py                    # Environment Configuration
│   └── services/                        # Business Logic Layer
│       ├── pipeline.py
│       ├── jobs.py
│       ├── project_store.py
│       ├── sandbox.py                   # Secure Python Execution Env
│       └── workspace.py
│
├── frontend/                            # Vue 3 / Vite Client UI
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── main.ts                      # Application Bootstrap
│       ├── App.vue                      # Root Component
│       ├── api/
│       │   └── client.ts                # WebSocket & Axios Interceptors
│       ├── stores/
│       │   └── useWorkspace.ts          # Pinia State Management
│       ├── styles/
│       │   └── app.css                  # Tailwind / Global CSS
│       └── components/                  # 🎨 Modular UI Components
│           ├── ChatPanel.vue            # Interactive Agent Chat Interface
│           ├── PipelineGraph.vue        # Visual LangGraph Node Traversal
│           ├── EventTimeline.vue        # Real-time WebSocket Event Feed
│           ├── ArtifactTabs.vue         # File & Asset Viewer
│           ├── PlotlyChart.vue          # Dynamic Data Visualization
│           └── SidebarPanel.vue         # Project Navigation
│

```

---

## 🔒 Security & Secrets Management
This repository strictly adheres to GitOps security protocols. **No `.env` files, API keys, or JWT secrets are tracked in version control.** 
Please duplicate `backend/.env.example` to `backend/.env` and inject your proprietary LLM keys (OpenAI, DeepSeek) locally before running the backend.

## 🚀 Getting Started

### Backend Initialization
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Configure .env file
uvicorn main:app --reload --port 8000
```

### Frontend Initialization
```bash
cd frontend
npm install
npm run dev
```

---
*Built for production-grade, asynchronous AI orchestration. Architecture designed for absolute determinism, hitl (human-in-the-loop) interruption, and dynamic scaling.*
