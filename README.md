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
    UI["Vue 3 Frontend Client"] <-->|"WebSocket / REST"| API["FastAPI Gateway"]
    
    API --> Supervisor["Supervisor Agent (State Machine)"]
    
    subgraph Swarm ["Multi-Agent Swarm (LangGraph)"]
        Supervisor --> Planner["Planner Agent"]
        Supervisor --> DataLoader["Data Loader Agent"]
        Supervisor --> Cleaning["Cleaning Agent"]
        Supervisor --> Feature["Feature Eng Agent"]
        Supervisor --> AutoML["AutoML / H2O Agent"]
        Supervisor --> Eval["Model Eval Agent"]
        Supervisor --> Vis["Visualization Agent"]
        
        Eval --> Reflexion["Reflexion / Critic Agent"]
        Reflexion -.->|"Feedback Loop"| AutoML
    end
    
    subgraph Core ["Core Engine"]
        MCP["MCP Governance"]
        Memory["PostgreSQL Checkpointer"]
        Idempotency["Idempotency Guard"]
    end
    
    Swarm --> Core
```

---

## 🧠 Core Agentic Paradigms (核心智能体架构)

Our engine is built upon three foundational multi-agent paradigms. These patterns ensure robust reasoning, resilient execution, and continuous self-improvement across the data science lifecycle.

### 1. Plan-and-Execute (计划与执行架构)

**Reference**: *Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning by Large Language Models* (Wang et al., 2023)

```mermaid
graph TD
    User(("🧑‍💻 User Query")) --> Planner["🧠 Planner Agent<br/>(Decompose task into steps)"]
    
    subgraph Execution Loop
        direction TB
        PlanQueue[("📋 Plan Queue")]
        Executor["🤖 Executor Agent<br/>(Executes single step)"]
        Tools[("🛠️ Tools / Environment")]
        Replanner["🔄 Replanner / Monitor<br/>(Evaluate & Update Plan)"]
        
        Planner --> PlanQueue
        PlanQueue -->|Pop Next Step| Executor
        Executor <-->|Use Tool| Tools
        Executor -->|Result| Replanner
        Replanner -->|Update/Append Steps| PlanQueue
    end
    
    Replanner -->|Task Complete| Output(("🎯 Final Answer"))
    
    classDef default fill:#f9f9eb,stroke:#333,stroke-width:1px;
    classDef agent fill:#e6e6fa,stroke:#7b68ee,stroke-width:2px;
    classDef io fill:#d4edda,stroke:#28a745,stroke-width:2px;
    
    class Planner,Executor,Replanner agent;
    class User,Output io;
```

**Core Prompt**:
> "You are an expert planner. For the given objective, come up with a simple step-by-step plan. This plan should involve individual tasks, that if executed correctly will yield the correct answer. Do not add any superfluous steps. The result of the final step should be the final answer. Make sure that each step has all the information needed - do not skip steps."

### 2. ReAct (Reasoning + Acting)

**Reference**: *ReAct: Synergizing Reasoning and Acting in Language Models* (Yao et al., 2022)

```mermaid
graph TD
    Input(("📥 Input Objective")) --> ReActAgent
    
    subgraph ReAct Loop [ReAct Iterative Loop]
        direction TB
        ReActAgent["🧠 ReAct Agent<br/>(LLM)"]
        
        Thought["💭 Thought<br/>(Reason about current state)"]
        Action["⚡ Action<br/>(Select Tool + Input)"]
        Obs["👁️ Observation<br/>(Tool Execution Result)"]
        
        ReActAgent --> Thought
        Thought --> Action
        Action --> Obs
        Obs -->|Feed back into Context| ReActAgent
    end
    
    Tools[("🛠️ External Tools<br/>(Search, API, Python)")]
    Action <-->|Execute| Tools
    
    ReActAgent -->|Finish| FinalAnswer(("🎯 Final Answer"))
    
    classDef default fill:#f9f9eb,stroke:#333,stroke-width:1px;
    classDef agent fill:#e6e6fa,stroke:#7b68ee,stroke-width:2px;
    classDef state fill:#ffe4e1,stroke:#ff69b4,stroke-width:1px;
    
    class ReActAgent agent;
    class Thought,Action,Obs state;
    class Input,FinalAnswer fill:#d4edda,stroke:#28a745,stroke-width:2px;
```

**Core Prompt**:
> "Use the following format: Question: the input question you must answer | Thought: you should always think about what to do | Action: the action to take, should be one of [{tool_names}] | Action Input: the input to the action | Observation: the result of the action | ... (this Thought/Action/Action Input/Observation can repeat N times) | Thought: I now know the final answer | Final Answer: the final answer to the original input question"

### 3. Reflection (反思与自我纠错)

**Reference**: *Reflexion: Language Agents with Verbal Reinforcement Learning* (Shinn et al., 2023)

```mermaid
graph TD
    Input(("📥 User Request")) --> Generator
    
    subgraph Reflection Framework
        direction TB
        Generator["✍️ Generator Agent<br/>(Drafts initial response/code)"]
        Env[("💻 Environment / Tests<br/>(Execution or Evaluator)")]
        Critic["🧐 Critic / Reflector Agent<br/>(Analyzes errors & provides feedback)"]
        
        Generator -->|Output Draft| Env
        Env -->|Execution Result / Error| Critic
        Critic -->|Constructive Feedback| Generator
    end
    
    Env -->|Success / Pass| Output(("✅ Final Validated Answer"))
    
    classDef default fill:#f9f9eb,stroke:#333,stroke-width:1px;
    classDef agent fill:#e6e6fa,stroke:#7b68ee,stroke-width:2px;
    
    class Generator,Critic agent;
    class Input,Output fill:#d4edda,stroke:#28a745,stroke-width:2px;
```

**Core Prompt**:
> "You are an expert reviewer and code critic. You are given a previous attempt at a task, the code/output generated, and the resulting execution error or test failure. Your job is to carefully analyze the failure, explain exactly WHY the previous attempt failed, and provide actionable, specific feedback on how to fix it. DO NOT write the code yourself, only provide the detailed reflection and instructions for the generator to fix the issue."

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
