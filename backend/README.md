# Backend

## Important Modules

- `main.py`: FastAPI application factory.
- `api/routes/*`: HTTP routes for sessions, datasets, chat, SSE, approvals and projects.
- `services/workspace.py`: session orchestration, dataset upload, supervisor invocation.
- `agents/supervisor.py`: LangGraph Plan-and-Execute/ReAct/Reflexion state machine.
- `core/llm.py`: private vLLM OpenAI-compatible client.
- `core/json_guard.py`: DFA JSON extraction + Pydantic schema validation.
- `core/events.py`: SSE asymmetric bus with graceful degradation.
- `core/storage.py`: hot/cold dataset storage.
- `core/security.py`: tenant context, SQL policy, HITL/prompt-injection guard.

## API Flow

1. `POST /api/v1/sessions`
2. `POST /api/v1/sessions/{id}/datasets/upload`
3. `GET /api/v1/sessions/{id}/events`
4. `POST /api/v1/sessions/{id}/chat`
5. Optional `POST /api/v1/sessions/{id}/approvals`

## Agent Flow

```text
PlannerAgent
  -> Specialist agent(s)
  -> ReflexionAgent on failure
  -> Max-Steps circuit breaker
  -> Artifacts + datasets + pipeline graph
```

Specialist agents are deliberately independent so they can be scaled, tested and
governed separately.

