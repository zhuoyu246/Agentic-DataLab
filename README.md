# 🚀 Agentic-DataLab: Multi-Agent Data Science Workflow Orchestrator

![License: Proprietary](https://img.shields.io/badge/License-Proprietary%20%2F%20All%20Rights%20Reserved-red.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Vue](https://img.shields.io/badge/vue-3.x-brightgreen)
![Status](https://img.shields.io/badge/status-Production--Ready-success)

Agentic-DataLab is an **Enterprise-Grade, Multi-Agent AI system** designed to fully automate the Data Science and Machine Learning lifecycle. Built on top of LangGraph's state machine architecture and an asynchronous FastAPI backend, it orchestrates a swarm of specialized AI agents to handle everything from data ingestion and cleaning to feature engineering, model training (AutoML/H2O), and evaluation.

The frontend is a robust Vue 3 + Vite application providing real-time WebSocket communication, event timelines, and dynamic Plotly visualizations.

---

## 📸 Workspace Showcase

Agentic-DataLab features a dynamic, real-time Vue 3 interface to track multi-agent interactions, pipeline execution, and data artifacts.

<div align="center">
  <img src="docs/images/showcase_1_login.png" alt="Agentic DataLab login" width="80%">
  <br/>
  <img src="docs/images/showcase_2_approval.png" alt="Agentic DataLab approval workflow" width="80%">
  <br/>
  <img src="docs/images/showcase_3_running.png" alt="Agentic DataLab running AutoML workflow" width="80%">
  <br/>
  <img src="docs/images/showcase_4_results.png" alt="Agentic DataLab model results and artifacts" width="80%">
  <br/>
  <img src="docs/images/showcase_5_usage.png" alt="Agentic DataLab usage analytics" width="80%">
  <br/>
  <img src="docs/images/showcase_6_pricing.png" alt="Agentic DataLab subscription plans" width="80%">
</div>

---

## 🏗️ System Architecture

Our system employs a strict separation of concerns, heavily utilizing the **Supervisor-Worker** multi-agent pattern with resilient memory checkpointing.

```mermaid
graph TD
    UI["Vue 3 Frontend Client"] <-->|"WebSocket / REST / SSE"| API["FastAPI Gateway"]
    
    API <-->|"Stream / Interrupt / Resume"| Supervisor["Supervisor Node (DFA Router)"]
    
    subgraph LangGraph ["LangGraph State Machine (Hub-and-Spoke Topology)"]
        direction TB
        Supervisor -->|"Strategic Planning"| Planner["Planner Agent"]
        Planner -->|"Execution Plan"| Supervisor
        
        Supervisor -->|"O(1) Conditional Edge"| Workers["10+ Specialist Workers<br/>(SQL, AutoML, Cleaning, etc.)"]
        Workers -->|"Return to Hub"| Supervisor
        
        Supervisor -.->|"Error Detected"| Reflexion["Reflexion Critic<br/>(Self-Correction)"]
        Reflexion -.->|"Revised Instruction"| Supervisor
        
        Supervisor -->|"HITL Approval"| Human["Human-in-the-Loop<br/>(interrupt_before)"]
        Human -->|"Command(resume)"| Supervisor
    end
    
    subgraph Core ["Industrial Core Infrastructure"]
        MCP["MCP Governance Layer<br/>(Validation & Rate Limits)"]
        Memory["Redis/Postgres Checkpointer<br/>(State Persistence & TTL)"]
        Reducer["Annotated Reducer<br/>(Sliding Window & Truncation)"]
    end
    
    LangGraph --> Core
```

---

## 🔄 End-to-End Interaction Flow (前后端交互全链路)

To handle high-concurrency LLM streaming and complex state pauses, the system employs an asynchronous event-driven architecture separating the REST API from the Server-Sent Events (SSE) bus.

```mermaid
sequenceDiagram
    autonumber
    actor User
    
    box Frontend (Vue 3)
    participant UI as Vue Components
    participant Pinia as State Store
    end
    
    box Backend (FastAPI)
    participant API as REST / SSE Routes
    participant EventBus as EventBus (Queue)
    end
    
    box LangGraph Engine
    participant Graph as Supervisor
    participant Worker as Agent
    participant Memory as Checkpointer
    end

    User->>UI: Submit Data Task
    UI->>Pinia: Action: sendMessage
    Pinia->>API: HTTP POST /chat (Trigger Execution)
    API->>EventBus: Open SSE Connection (Subscribe)
    API->>Graph: Invoke State Machine (Async Thread)
    
    rect rgb(240, 248, 255)
        note right of EventBus: Phase 1: Asynchronous Streaming
        Graph->>Worker: Dispatch Sub-task
        Worker-->>EventBus: publish(AgentEvent)
        EventBus-->>Pinia: SSE Yield (Event stream)
        Pinia-->>UI: Reactive DOM Update (60fps)
    end
    
    rect rgb(255, 240, 245)
        note right of EventBus: Phase 2: QueueFull Graceful Degradation
        Worker-->>EventBus: publish(Verbose LLM Log)
        EventBus-->>EventBus: Queue Full! Drop old log
        EventBus-->>EventBus: Insert DEGRADED warning
        EventBus-->>Pinia: SSE Yield (warning: degraded)
        Pinia-->>UI: Render "Backpressure" state
    end
    
    rect rgb(255, 250, 240)
        note right of EventBus: Phase 3: Human-in-the-Loop (HITL)
        Worker->>Graph: Request Approval (interrupt)
        Graph->>Memory: Persist current state & Pause
        Graph-->>EventBus: publish(approval_required)
        EventBus-->>Pinia: SSE Yield (approval UI trigger)
        Pinia-->>UI: Render Approve/Reject Buttons
        
        User->>UI: Click "Approve"
        UI->>Pinia: Action: submitApproval
        Pinia->>API: HTTP POST /approvals (Resume)
        API->>Graph: Command(resume={"action":"approve"})
        Graph->>Memory: Restore state & Resume execution
        Graph->>Worker: Execute risky tool
    end
```

---

## 🧠 Core Agentic Paradigms (核心智能体架构)

Our engine is built upon three foundational multi-agent paradigms. These patterns ensure robust reasoning, resilient execution, and continuous self-improvement across the data science lifecycle.

### 1. Plan-and-Execute (计划与执行架构)

**Reference**: *Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning by Large Language Models* (Wang et al., 2023)

```mermaid
graph TD
    User(("🧑‍💻 User Query")) --> Planner["🧠 Planner Agent<br/>(Decompose task into steps)"]
    
    subgraph ExecutionLoop [Execution Loop]
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
> "You are an elite Enterprise Data Science Architect and Macro Planner. Your sole job is to decompose the user's analytical goal into a sequence of executable steps. You are a STRATEGIST — you NEVER execute tools yourself. Each step must be assigned to exactly one specialist agent. Keep the plan minimal — do NOT add superfluous steps. Return ONLY strict JSON."

### 2. ReAct (Reasoning + Acting)

**Reference**: *ReAct: Synergizing Reasoning and Acting in Language Models* (Yao et al., 2022)

```mermaid
graph TD
    Input(("📥 Input Objective")) --> ReActAgent
    
    subgraph ReActLoop [ReAct Iterative Loop]
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
    
    Tools[("🛠️ External Tools<br/>(MCP Governance Layer)")]
    Action <-->|Execute| Tools
    
    ReActAgent -->|Finish / Max Iters| FinalAnswer(("🎯 Final Answer"))
    
    classDef default fill:#f9f9eb,stroke:#333,stroke-width:1px;
    classDef agent fill:#e6e6fa,stroke:#7b68ee,stroke-width:2px;
    classDef state fill:#ffe4e1,stroke:#ff69b4,stroke-width:1px;
    
    class ReActAgent agent;
    class Thought,Action,Obs state;
    class Input,FinalAnswer fill:#d4edda,stroke:#28a745,stroke-width:2px;
```

**Core Prompt**:
> "You are a ReAct-based AI assistant that solves complex tasks through iterative reasoning and tool usage. You MUST follow the structured Thought-Action-Observation loop strictly. ALWAYS start with a 'thought' that analyzes the current state. If a tool returns an error, reflect on WHY it failed and try a different approach. You have a maximum of 5 iterations. Use them wisely."

### 3. Reflection (反思与自我纠错)

**Reference**: *Reflexion: Language Agents with Verbal Reinforcement Learning* (Shinn et al., 2023)

```mermaid
graph TD
    Input(("📥 User Request")) --> Generator
    
    subgraph ReflectionFramework [Reflection Framework]
        direction TB
        Generator["✍️ Generator Agent<br/>(Drafts initial response/code)"]
        Env[("💻 Environment / Tests<br/>(Execution or Evaluator)")]
        Critic["🧐 Critic / Reflector Agent<br/>(Analyzes errors & provides feedback)"]
        
        Generator -->|Output Draft| Env
        Env -->|Execution Result / Error| Critic
        Critic -->|Constructive Feedback| Generator
    end
    
    Env -->|Success / Pass| Output(("✅ Final Validated Answer"))
    Critic -.->|"Circuit Breaker (Max Depth = 3)"| Output
    
    classDef default fill:#f9f9eb,stroke:#333,stroke-width:1px;
    classDef agent fill:#e6e6fa,stroke:#7b68ee,stroke-width:2px;
    
    class Generator,Critic agent;
    class Input,Output fill:#d4edda,stroke:#28a745,stroke-width:2px;
```

**Core Prompt**:
> "You are an expert reviewer, code critic, and debugging specialist. You are given a PREVIOUS ATTEMPT at a task that FAILED. Your job is to: 1. Carefully analyze the failure and explain exactly WHY it happened. 2. Identify the ROOT CAUSE. 3. Provide ACTIONABLE, SPECIFIC feedback on how to fix it. 4. Suggest a revised instruction that avoids the same mistake. Do NOT write the actual code yourself."

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
