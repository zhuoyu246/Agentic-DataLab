# Agentic DataLab

Enterprise private multi-agent data-science platform. This project is a clean
front/back separated rewrite inspired by `ai-data-science-team`, without
modifying that source tree.

## Scope

Agentic DataLab keeps the original data-science capability surface:

- data loading and dataset registry
- data cleaning and wrangling
- EDA summaries and profiling
- Plotly visualization with fallback charts
- SQL database agent with guarded execution
- feature engineering
- AutoML flow
- MLflow experiment integration
- model evaluation artifacts
- pipeline lineage graph
- project save/load
- chat-first supervisor workflow

It then adds enterprise/private deployment concerns:

- FastAPI backend + Vue frontend separation
- LangGraph supervisor state machine
- private vLLM OpenAI-compatible inference client
- PagedAttention-aware deployment contract on the vLLM side
- DFA JSON extraction + Pydantic validation
- SSE asymmetric event bus with slow-client graceful degradation
- hot/cold dataset storage split
- sliding-window context trimming and dataframe metadata compression
- idempotency locks for double-submit and cost control
- Max-Steps circuit breaker for Agent loop prevention
- SQL least-privilege policy, HITL approvals and prompt-injection heuristics
- checkpoint snapshots with time-travel-compatible history
- MCP registry placeholder for future cross-tool protocol exposure

## Architecture

```text
frontend/
  Vue 3 + Vite + Pinia + Vue Flow
  ├─ Sidebar: tenant/model/HITL/MLflow/H2O controls
  ├─ Chat: supervisor interaction
  ├─ Pipeline: lineage graph
  ├─ Artifacts: EDA/SQL/charts/models
  └─ SSE timeline

backend/
  FastAPI
  ├─ api/routes: HTTP boundary
  ├─ services: sessions, projects, jobs, sandbox, pipeline graph
  ├─ agents: planner/react/reflexion + specialist agents
  ├─ core: vLLM, JSON Guard, SSE, checkpoint, security, storage
  └─ schemas: Pydantic contracts
```

## Backend Quickstart

```bash
cd Agentic-DataLab/backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

If no vLLM endpoint is running, the planner gracefully falls back to a deterministic
heuristic planner. Specialist tools still run locally.

## Frontend Quickstart

```bash
cd Agentic-DataLab/frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## vLLM Deployment Contract

Agentic DataLab talks to vLLM through the OpenAI-compatible
`/v1/chat/completions` API. PagedAttention is a vLLM runtime optimization; it is
enabled and tuned in the vLLM server process, while this app controls:

- model name
- base URL
- timeout
- context trimming
- strict JSON validation
- planner fallback

Example:

```bash
python -m vllm.entrypoints.openai.api_server ^
  --model Qwen/Qwen2.5-7B-Instruct ^
  --host 0.0.0.0 ^
  --port 8001 ^
  --gpu-memory-utilization 0.90
```

## DeepSeek API Mode

DeepSeek can be used first because it exposes an OpenAI-compatible API. Copy the
DeepSeek env template and restart the backend:

```bash
cd Agentic-DataLab/backend
copy .env.deepseek.example .env
```

Then edit `.env`:

```text
VLLM_BASE_URL=https://api.deepseek.com/v1
VLLM_MODEL=deepseek-chat
VLLM_API_KEY=sk-your-real-deepseek-key
```

Restart FastAPI after changing `.env`. The current `VLLM_*` variable names are
kept intentionally because both local vLLM and DeepSeek use the same
OpenAI-compatible `/v1/chat/completions` protocol.

## Safety Model

The backend separates control flow from data flow:

- LLM receives compact metadata, not raw full datasets.
- Dataframes live in `DatasetStorage` with hot/cold separation.
- SQL writes are blocked unless policy and HITL approvals allow them.
- The supervisor has hard `MAX_AGENT_STEPS` and Reflexion retry limits.
- SSE backpressure never blocks agent execution.
- Checkpoints are TTL-based and can be replaced by Redis/PostgreSQL later.

## Current Status

This is a commercial-grade foundation, not a toy single-file demo. It is ready
for iterative hardening: authentication, PostgreSQL persistence, Redis queues,
real H2O cluster scheduling, model registry governance and deployment packaging.
