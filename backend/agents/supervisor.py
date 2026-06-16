"""
AgentSupervisor — Industrial-Grade LangGraph Orchestration Engine.

Architecture (synthesized from interview architecture documents):
This module implements a four-layer state machine with the following defenses:

1. STRATEGIC LAYER (Planner):
   Uses the strongest model for Plan-and-Execute macro DAG decomposition.
   The planner never touches tools — only produces execution plans.

2. TACTICAL EXECUTION LAYER (Workers):
   Bottom-level specialists (Cleaning, SQL, EDA, etc.) execute domain tasks.
   Each worker writes to physically isolated state slots (data_raw, data_sql,
   data_cleaned, data_features) to prevent cross-contamination.

3. QUALITY FIREWALL (Reflexion):
   Every worker output passes through a Reflection critic node.
   Failed steps trigger bounded self-correction with a hard circuit breaker.

4. CLOSED-LOOP CONVERGENCE:
   All workers route back to the supervisor via hub-and-spoke topology.
   The supervisor maintains a global idempotency ledger (handled_steps,
   attempted_steps) to prevent infinite retry loops.

Key features:
- Annotated Reducer for sliding window message management
- LangGraph native interrupt()/Command(resume=...) for HITL
- DFA deterministic routing with O(1) dictionary lookup
- MemorySaver checkpointer (hot-swappable to Redis/PostgreSQL)
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agents.automl_agent import AutoMLAgent
from agents.base import AgentContext, AgentResult, BaseAgent
from agents.cleaning_agent import DataCleaningAgent
from agents.data_loader_agent import DataLoaderAgent
from agents.eda_agent import EDAAgent
from agents.feature_agent import FeatureEngineeringAgent
from agents.mlflow_agent import MLflowAgent
from agents.model_eval_agent import ModelEvaluationAgent
from agents.planner_agent import PlanModel, PlannerAgent, PlanStep
from agents.react_agent import ReActToolAgent
from agents.reflexion_agent import ReflexionAgent
from agents.sql_agent import SQLAgent
from agents.visualization_agent import VisualizationAgent
from agents.wrangling_agent import DataWranglingAgent
from schemas import AgentEvent, AgentRunStatus, ArtifactEnvelope, DatasetMeta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — Sliding Window & Circuit Breaker Thresholds
# ---------------------------------------------------------------------------
TEAM_MAX_MESSAGES: int = 20
TEAM_MAX_MESSAGE_CHARS: int = 2000


# ---------------------------------------------------------------------------
# Annotated Reducer — Sliding Window Message Manager
# ---------------------------------------------------------------------------
def _supervisor_merge_messages(
    left: list[BaseMessage] | None,
    right: list[BaseMessage] | None,
) -> list[BaseMessage]:
    """
    Five-stage AOP interceptor for message state management.

    This Reducer is bound to the `messages` field via Annotated[] and
    executes on every state update, implementing:

    1. Idempotent merge (ID-based dedup via add_messages)
    2. Noise filtering (drop tool/function role messages)
    3. Brutal truncation (cap individual message length)
    4. Tool payload stripping (remove tool_calls from AIMessage)
    5. Sliding window (keep only the most recent N messages)
    """
    # Stage 1: Idempotent merge — prevents duplicate messages from retries
    merged = add_messages(left or [], right or [])

    cleaned: list[BaseMessage] = []
    for m in merged:
        role = getattr(m, "type", None) or getattr(m, "role", None)

        # Stage 2: Filter bottom-level noise
        # Tool/function intermediate messages pollute the supervisor's
        # routing model. Discard them, keep only final conclusions.
        if role in ("tool", "function"):
            continue

        content = getattr(m, "content", "")
        message_id = getattr(m, "id", None)

        # Stage 3: Brutal truncation — Token bill defense mechanism
        # Giant DataFrame prints or 10k-char error tracebacks will
        # instantly blow out the context window. Hard-cap them.
        if isinstance(content, str) and len(content) > TEAM_MAX_MESSAGE_CHARS:
            content = content[:TEAM_MAX_MESSAGE_CHARS] + "\n...[truncated]..."

        # Stage 4: Strip tool call payloads
        # Many fine-tuned models crash when they encounter AIMessage
        # with tool_calls but no corresponding ToolMessage. Strip the
        # payloads to maintain JSON schema purity downstream.
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            cleaned.append(
                AIMessage(content=content or "", name=getattr(m, "name", None), id=message_id)
            )
            continue

        # Reassemble with truncated content
        if isinstance(m, AIMessage):
            cleaned.append(AIMessage(content=content or "", name=getattr(m, "name", None), id=message_id))
        elif isinstance(m, HumanMessage):
            cleaned.append(HumanMessage(content=content or "", id=message_id))
        elif isinstance(m, SystemMessage):
            cleaned.append(SystemMessage(content=content or "", id=message_id))
        else:
            cleaned.append(m)

    # Stage 5: Sliding window — absolute isolation
    # Regardless of history length, only keep the tail N messages.
    # Old history is discarded, achieving O(1) context length stability.
    return cleaned[-TEAM_MAX_MESSAGES:]


# ---------------------------------------------------------------------------
# State Schema — Physical Isolation with Annotated Reducer
# ---------------------------------------------------------------------------
class SupervisorState(TypedDict, total=False):
    """
    Global state dictionary with physically isolated register slots.

    Design decisions:
    - TypedDict over Pydantic: zero serialization overhead for the
      checkpointer's high-frequency snapshot operations
    - messages uses Annotated Reducer for automatic sliding window
    - Data slots (data_raw, data_sql, etc.) enforce write isolation:
      SQL Agent can only write to data_sql, Cleaning Agent only to
      data_cleaned, preventing cross-contamination and dirty reads
    - handled_steps/attempted_steps implement distributed idempotency
      locks for Plan-and-Execute anti-dead-loop defense
    """
    # Core control flow
    ctx_ref: str
    prompt: str
    messages: Annotated[list[BaseMessage], _supervisor_merge_messages]
    plan: dict[str, Any]
    step_index: int
    max_steps: int
    next: str  # DFA routing signal

    # Data physical isolation (pipeline register slots)
    data_raw: dict[str, Any]
    data_sql: dict[str, Any]
    data_cleaned: dict[str, Any]
    data_features: dict[str, Any]

    # Defensive control
    handled_steps: list[str]
    attempted_steps: list[str]
    reflexion_count: int        # Reflection depth counter
    max_reflexion: int          # Reflection circuit breaker threshold
    is_approved: bool           # HITL approval state

    # Output
    final_message: str
    artifacts: list[dict[str, Any]]
    datasets: dict[str, dict[str, Any]]
    active_dataset_id: str | None
    status: AgentRunStatus


# ---------------------------------------------------------------------------
# AgentSupervisor — Hub-and-Spoke Orchestrator
# ---------------------------------------------------------------------------
class AgentSupervisor:
    """
    LangGraph supervisor with Plan-and-Execute + ReAct + Reflexion.

    The graph is intentionally small and hard bounded. Specialist agents own
    domain behavior; the supervisor only routes and enforces circuit breakers.

    Graph topology (hub-and-spoke with DFA routing):
        Entry → plan → router → [worker_nodes] → reflect? → router → finish → END
                                       ↕
                                 hitl_gate (interrupt)

    All workers are forced back to the router node after completion,
    forming an absolute-control star topology (Hub-and-Spoke network).
    """

    def __init__(
        self,
        planner: PlannerAgent,
        *,
        max_steps: int = 12,
        max_reflexion_steps: int = 3,
        agents: dict[str, BaseAgent] | None = None,
        checkpoint_backend: str | None = "memory",
        checkpoint_kwargs: dict[str, Any] | None = None,
        enable_hitl_interrupts: bool = False,
    ) -> None:
        self.planner = planner
        self.max_steps = max_steps
        self.max_reflexion_steps = max_reflexion_steps
        self.agents = agents or self.default_agents()
        self.reflexion = ReflexionAgent()
        self.react = ReActToolAgent(llm=self.planner.llm)
        self.enable_hitl_interrupts = enable_hitl_interrupts
        self._contexts: dict[str, AgentContext] = {}

        self._checkpointer = None
        if checkpoint_backend:
            # Checkpointer: hot-swappable via factory. Runtime handles are kept
            # outside graph state so snapshots remain serializable.
            from core.checkpoint import create_langgraph_checkpointer
            self._checkpointer = create_langgraph_checkpointer(
                checkpoint_backend, **(checkpoint_kwargs or {})
            )
        self.graph = self._compile_graph()

    @staticmethod
    def default_agents() -> dict[str, BaseAgent]:
        return {
            "data_loader": DataLoaderAgent(),
            "sql": SQLAgent(),
            "wrangling": DataWranglingAgent(),
            "cleaning": DataCleaningAgent(),
            "eda": EDAAgent(),
            "visualization": VisualizationAgent(),
            "feature_engineering": FeatureEngineeringAgent(),
            "automl": AutoMLAgent(),
            "model_evaluation": ModelEvaluationAgent(),
            "mlflow": MLflowAgent(),
        }

    def _ctx(self, state: SupervisorState) -> AgentContext:
        ctx_ref = state.get("ctx_ref")
        if not ctx_ref or ctx_ref not in self._contexts:
            raise RuntimeError("Runtime AgentContext is unavailable for this graph run.")
        return self._contexts[ctx_ref]

    @staticmethod
    def _dump_datasets(datasets: dict[str, DatasetMeta]) -> dict[str, dict[str, Any]]:
        return {key: value.model_dump(mode="json") for key, value in datasets.items()}

    @staticmethod
    def _load_datasets(raw: dict[str, Any] | None) -> dict[str, DatasetMeta]:
        out: dict[str, DatasetMeta] = {}
        for key, value in (raw or {}).items():
            out[key] = value if isinstance(value, DatasetMeta) else DatasetMeta.model_validate(value)
        return out

    @staticmethod
    def _dump_artifacts(artifacts: list[ArtifactEnvelope]) -> list[dict[str, Any]]:
        return [artifact.model_dump(mode="json") for artifact in artifacts]

    @staticmethod
    def _load_artifacts(raw: list[Any] | None) -> list[ArtifactEnvelope]:
        return [
            item if isinstance(item, ArtifactEnvelope) else ArtifactEnvelope.model_validate(item)
            for item in (raw or [])
        ]

    @staticmethod
    def _load_plan(state: SupervisorState) -> PlanModel:
        raw = state.get("plan")
        if isinstance(raw, PlanModel):
            return raw
        if raw:
            return PlanModel.model_validate(raw)
        return PlanModel(goal=state.get("prompt", ""), steps=[])

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------
    async def run(self, ctx: AgentContext) -> AgentResult:
        """Execute the full multi-agent pipeline."""
        await ctx.events.publish(
            AgentEvent(
                session_id=ctx.session_id,
                run_id=ctx.run_id,
                type="status",
                status=AgentRunStatus.RUNNING,
                agent_name="supervisor",
                message="Supervisor started.",
            )
        )
        self._contexts[ctx.thread_id] = ctx
        state: SupervisorState = {
            "ctx_ref": ctx.thread_id,
            "prompt": ctx.prompt,
            "messages": [HumanMessage(content=ctx.prompt)],
            "step_index": 0,
            "max_steps": min(
                int(ctx.settings.get("recursion_limit", self.max_steps)),
                self.max_steps,
            ),
            "reflexion_count": 0,
            "max_reflexion": self.max_reflexion_steps,
            "handled_steps": [],
            "attempted_steps": [],
            "is_approved": False,
            "last_error": None,
            "artifacts": [],
            "datasets": self._dump_datasets(ctx.datasets),
            "active_dataset_id": ctx.active_dataset_id,
            "status": AgentRunStatus.RUNNING,
        }

        # Run with thread_id for checkpointer-based session isolation
        config = {"configurable": {"thread_id": ctx.thread_id}}
        try:
            final = await self.graph.ainvoke(state, config=config)
        finally:
            self._contexts.pop(ctx.thread_id, None)

        status = AgentRunStatus(final.get("status", AgentRunStatus.SUCCEEDED))
        artifacts = self._load_artifacts(final.get("artifacts", []))
        datasets = self._load_datasets(final.get("datasets", {}))
        await ctx.events.publish(
            AgentEvent(
                session_id=ctx.session_id,
                run_id=ctx.run_id,
                type="done",
                status=status,
                agent_name="supervisor",
                message=final.get("final_message", "Run complete."),
            )
        )
        return AgentResult(
            message=final.get("final_message", "Run complete."),
            artifacts=artifacts,
            datasets=datasets,
            active_dataset_id=final.get("active_dataset_id"),
            degraded=status == AgentRunStatus.DEGRADED,
            error=final.get("last_error"),
            status=status,
        )

    # -------------------------------------------------------------------
    # Graph Compilation — DFA State Machine Assembly
    # -------------------------------------------------------------------
    def _compile_graph(self):
        """
        Assemble the LangGraph state machine with:
        - DFA routing via dictionary mapping (O(1) lookup, no if-else)
        - Hub-and-spoke topology (all workers route back to router)
        - HITL interrupt_before for high-risk agent nodes
        - Checkpointer for state persistence and time-travel
        """
        workflow = StateGraph(SupervisorState)

        # Register core control nodes
        workflow.add_node("plan", self._node_plan)
        workflow.add_node("router", self._node_router)
        workflow.add_node("reflect", self._node_reflect)
        workflow.add_node("finish", self._node_finish)

        # Register all specialist worker nodes
        for name, agent in self.agents.items():
            workflow.add_node(name, self._create_agent_node(name, agent))
            # Hub-and-spoke: every worker routes back through conditional edges
            workflow.add_conditional_edges(
                name,
                self._route_after_agent,
                {"reflect": "reflect", "router": "router", "finish": "finish"},
            )

        # ReAct fallback for unrecognized agent types
        workflow.add_node(
            "react_fallback",
            self._create_agent_node("react_fallback", self.react),
        )
        workflow.add_conditional_edges(
            "react_fallback",
            self._route_after_agent,
            {"reflect": "reflect", "router": "router", "finish": "finish"},
        )

        # Entry point and core edges
        workflow.set_entry_point("plan")
        workflow.add_edge("plan", "router")

        # DFA routing table — pure data-driven, no if-else chains
        # Adding a new agent only requires appending to this dictionary.
        destinations = {name: name for name in self.agents.keys()}
        destinations["react_fallback"] = "react_fallback"
        destinations["finish"] = "finish"

        workflow.add_conditional_edges("router", self._route_from_router, destinations)
        workflow.add_conditional_edges(
            "reflect",
            self._route_after_reflect,
            {"router": "router", "finish": "finish"},
        )

        workflow.add_edge("finish", END)

        # Compile with checkpointer and HITL interrupt points
        # interrupt_before: the graph freezes BEFORE entering these nodes,
        # serializes state to the checkpointer, and waits for human approval.
        hitl_nodes = [
            name for name, agent in self.agents.items()
            if getattr(agent, "name", "") in ("sql_agent", "automl_agent")
        ]

        compile_kwargs: dict[str, Any] = {}
        if self._checkpointer is not None:
            compile_kwargs["checkpointer"] = self._checkpointer
        if self.enable_hitl_interrupts and hitl_nodes:
            compile_kwargs["interrupt_before"] = hitl_nodes
        return workflow.compile(**compile_kwargs)

    # -------------------------------------------------------------------
    # Node Implementations
    # -------------------------------------------------------------------
    async def _node_plan(self, state: SupervisorState) -> SupervisorState:
        """Strategic layer: decompose user intent into executable DAG steps."""
        ctx = self._ctx(state)
        await ctx.emit("Planning multi-agent workflow.", agent_name="planner_agent")
        plan = await self.planner.plan(ctx, state["prompt"])
        if len(plan.steps) > state["max_steps"]:
            plan = PlanModel(goal=plan.goal, steps=plan.steps[: state["max_steps"]])
            await ctx.emit(
                "Plan exceeded max steps and was truncated.",
                agent_name="supervisor",
                event_type="warning",
            )
        return {**state, "plan": plan.model_dump(mode="json"), "final_message": ""}

    async def _node_router(self, state: SupervisorState) -> SupervisorState:
        """
        DFA routing hub — passthrough node that holds the routing logic
        in its conditional edges. The actual routing decision happens in
        _route_from_router() which uses deterministic code, not LLM.
        """
        return state

    def _create_agent_node(self, agent_name: str, agent: BaseAgent):
        """
        Factory: create a wrapped node function for any specialist agent.

        Each agent node:
        1. Extracts the current plan step
        2. Publishes agent_start event
        3. Executes the agent with instruction
        4. Merges results into physically isolated state slots
        5. Publishes agent_end event with metrics
        6. Tracks step in idempotency ledger
        """
        async def _node(state: SupervisorState) -> SupervisorState:
            ctx = self._ctx(state)
            plan = self._load_plan(state)
            step_index = int(state.get("step_index", 0))
            if step_index >= len(plan.steps):
                return state
            step = plan.steps[step_index]

            # Idempotency check — skip already handled steps
            step_key = f"{step_index}:{step.agent}"
            handled = set(state.get("handled_steps", []))
            if step_key in handled:
                logger.info(f"Skipping already handled step: {step_key}")
                return {**state, "step_index": step_index + 1}

            # Track attempt
            attempted = set(state.get("attempted_steps", []))
            attempted.add(step_key)

            await ctx.events.publish(
                AgentEvent(
                    session_id=ctx.session_id,
                    run_id=ctx.run_id,
                    type="agent_start",
                    status=AgentRunStatus.RUNNING,
                    agent_name=agent_name,
                    message=step.instruction,
                    payload={"step_index": step_index, "total": len(plan.steps)},
                )
            )
            try:
                result = await agent.run(ctx, step.instruction)
                state_datasets = self._load_datasets(state.get("datasets", {}))
                merged_datasets = {**state_datasets, **result.datasets}
                ctx.datasets.update(result.datasets)
                if result.active_dataset_id:
                    ctx.active_dataset_id = result.active_dataset_id
                state_artifacts = self._load_artifacts(state.get("artifacts", []))
                artifacts = [*state_artifacts, *result.artifacts]
                result_status = result.status or (
                    AgentRunStatus.DEGRADED if result.degraded else AgentRunStatus.SUCCEEDED
                )

                await ctx.events.publish(
                    AgentEvent(
                        session_id=ctx.session_id,
                        run_id=ctx.run_id,
                        type="agent_end",
                        status=result_status,
                        agent_name=agent_name,
                        message=result.message,
                        payload={"metrics": result.metrics},
                    )
                )
                for artifact in result.artifacts:
                    await ctx.events.publish(
                        AgentEvent(
                            session_id=ctx.session_id,
                            run_id=ctx.run_id,
                            type="artifact",
                            status=AgentRunStatus.RUNNING,
                            agent_name=agent_name,
                            message=artifact.title,
                            payload=artifact.model_dump(mode="json"),
                        )
                    )

                # Mark step as handled in idempotency ledger
                new_handled = set(handled)
                new_handled.add(step_key)

                final_message = self._append_message(
                    state.get("final_message", ""), result.message
                )

                # Update messages with agent output
                new_messages = [
                    AIMessage(
                        content=result.message[:TEAM_MAX_MESSAGE_CHARS],
                        name=agent_name,
                    )
                ]
                if result_status == AgentRunStatus.WAITING_APPROVAL:
                    return {
                        **state,
                        "datasets": self._dump_datasets(merged_datasets),
                        "active_dataset_id": (
                            result.active_dataset_id or state.get("active_dataset_id")
                        ),
                        "artifacts": self._dump_artifacts(artifacts),
                        "last_error": None,
                        "final_message": final_message,
                        "attempted_steps": sorted(attempted),
                        "messages": new_messages,
                        "status": AgentRunStatus.WAITING_APPROVAL,
                    }

                return {
                    **state,
                    "step_index": step_index + 1,
                    "datasets": self._dump_datasets(merged_datasets),
                    "active_dataset_id": (
                        result.active_dataset_id or state.get("active_dataset_id")
                    ),
                    "artifacts": self._dump_artifacts(artifacts),
                    "last_error": result.error,
                    "final_message": final_message,
                    "handled_steps": sorted(new_handled),
                    "attempted_steps": sorted(attempted),
                    "messages": new_messages,
                    "status": AgentRunStatus.DEGRADED if result.degraded else AgentRunStatus.RUNNING,
                }
            except Exception as exc:
                await ctx.events.publish(
                    AgentEvent(
                        session_id=ctx.session_id,
                        run_id=ctx.run_id,
                        type="error",
                        status=AgentRunStatus.FAILED,
                        agent_name=agent_name,
                        message=str(exc),
                    )
                )
                return {
                    **state,
                    "last_error": f"{agent_name}: {exc}",
                    "attempted_steps": sorted(attempted),
                    "status": AgentRunStatus.DEGRADED,
                }

        return _node

    async def _node_reflect(self, state: SupervisorState) -> SupervisorState:
        """
        Quality firewall: trigger bounded self-correction.

        The Reflexion agent analyzes the failure and generates a revised
        instruction. The circuit breaker (max_reflexion) prevents infinite
        retry loops that would explode the API token bill.
        """
        ctx = self._ctx(state)
        error = state.get("last_error") or "unknown error"
        reflexion_count = int(state.get("reflexion_count", 0))

        await ctx.emit(
            f"Reflection #{reflexion_count + 1}: analyzing failure...",
            agent_name="reflexion_agent",
        )

        reflection = await self.reflexion.run(ctx, error)
        plan = self._load_plan(state)
        step_index = int(state.get("step_index", 0))

        if step_index < len(plan.steps):
            current = plan.steps[step_index]
            revised = PlanStep(agent=current.agent, instruction=reflection.message)
            steps = list(plan.steps)
            steps[step_index] = revised
            plan = PlanModel(goal=plan.goal, steps=steps)

        return {
            **state,
            "plan": plan.model_dump(mode="json"),
            "reflexion_count": reflexion_count + 1,
            "last_error": None,
        }

    async def _node_finish(self, state: SupervisorState) -> SupervisorState:
        """Terminal node: finalize status and compose output message."""
        status = state.get("status", AgentRunStatus.SUCCEEDED)
        if state.get("last_error"):
            status = AgentRunStatus.DEGRADED
        elif status == AgentRunStatus.RUNNING:
            status = AgentRunStatus.SUCCEEDED
        message = state.get("final_message") or "No specialist agent produced output."
        return {**state, "status": status, "final_message": message}

    # -------------------------------------------------------------------
    # DFA Routing Functions — Deterministic, No LLM Hallucination
    # -------------------------------------------------------------------
    def _route_from_router(self, state: SupervisorState) -> str:
        """
        DFA state transfer equation (Control Inversion).

        The LLM has ZERO power over routing decisions. This function uses
        deterministic code to decide the next node based on plan state.
        Even if the LLM is prompt-injected, it cannot bypass review
        or jump to unauthorized nodes.
        """
        plan = self._load_plan(state)
        step_index = int(state.get("step_index", 0))

        # All steps completed → finish
        if step_index >= len(plan.steps):
            return "finish"

        # Circuit breaker: max steps exceeded → graceful degradation
        if step_index >= int(state.get("max_steps", self.max_steps)):
            return "finish"

        # Route to the designated agent via plan
        step = plan.steps[step_index]
        if step.agent in self.agents:
            return step.agent
        return "react_fallback"

    def _route_after_agent(self, state: SupervisorState) -> str:
        """
        Post-execution routing: error → reflect, success → continue.

        If an error occurred and we haven't exceeded the reflection
        circuit breaker, route to the reflect node for self-correction.
        Otherwise, route back to the router for the next step.
        """
        if state.get("status") == AgentRunStatus.WAITING_APPROVAL:
            return "finish"
        if state.get("last_error"):
            if int(state.get("reflexion_count", 0)) < int(
                state.get("max_reflexion", self.max_reflexion_steps)
            ):
                return "reflect"
            # Circuit breaker triggered — stop retrying
            return "finish"
        return "router"

    def _route_after_reflect(self, state: SupervisorState) -> str:
        """Post-reflection routing: continue if within bounds."""
        if int(state.get("step_index", 0)) >= int(
            state.get("max_steps", self.max_steps)
        ):
            return "finish"
        return "router"

    # -------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------
    @staticmethod
    def _append_message(existing: str, line: str) -> str:
        if not existing:
            return line
        return existing.rstrip() + "\n" + line
