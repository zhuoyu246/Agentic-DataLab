"""
Base Agent Framework — Industrial-Grade LangGraph Foundation.

Provides AgentContext (shared state carrier), AgentResult (typed output),
and BaseAgent (protocol contract) used by every specialist agent.

Design Decisions (from architecture review documents):
- AgentContext carries a composite thread_id (usr-{user_id}_thd-{uuid4})
  to guarantee zero-collision session isolation in distributed clusters.
- HITL configuration is injected here so any agent can query whether
  it needs human approval before executing a destructive action.
- TypedDict is preferred over Pydantic for internal state to achieve
  zero-serialization-overhead with the LangGraph Checkpointer.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from core.events import EventBus
from core.security import SecurityPolicy, TenantContext
from core.storage import DatasetStorage
from schemas import AgentEvent, AgentRunStatus, ArtifactEnvelope, DatasetMeta


# ---------------------------------------------------------------------------
# HITL Configuration
# ---------------------------------------------------------------------------
DEFAULT_HITL_TOOLS: frozenset[str] = frozenset({
    "sql.execute",
    "python.exec",
    "mlflow.transition_model",
    "automl.train",
})


@dataclass
class AgentContext:
    """
    Shared execution context passed through the entire LangGraph state machine.

    Every specialist agent receives this object, which carries tenant identity,
    storage handles, event bus, security policy, and HITL configuration.
    The thread_id follows the Prefixed Composite ID design:
        usr-{user_id}_thd-{uuid4}
    This guarantees zero-collision in distributed deployments and enables
    O(1) index-based session tracing and sharding-ready data locality.
    """
    session_id: str
    run_id: str
    tenant: TenantContext
    prompt: str
    active_dataset_id: str | None
    storage: DatasetStorage
    events: EventBus
    security: SecurityPolicy
    # Composite thread ID for checkpointer-based memory isolation
    thread_id: str = field(default_factory=lambda: "")
    history: list[dict[str, str]] = field(default_factory=list)
    datasets: dict[str, DatasetMeta] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    approvals: dict[str, bool] = field(default_factory=dict)
    # HITL: set of tool names that require human approval
    hitl_tools: frozenset[str] = field(default_factory=lambda: DEFAULT_HITL_TOOLS)

    def __post_init__(self) -> None:
        if not self.thread_id:
            self.thread_id = f"usr-{self.tenant.user_id}_thd-{uuid.uuid4()}"

    async def emit(
        self,
        message: str,
        *,
        agent_name: str | None = None,
        event_type: str = "status",
        status: AgentRunStatus | None = AgentRunStatus.RUNNING,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self.events.publish(
            AgentEvent(
                session_id=self.session_id,
                run_id=self.run_id,
                type=event_type,  # type: ignore[arg-type]
                status=status,
                agent_name=agent_name,
                message=message,
                payload=payload or {},
            )
        )

    def active_dataframe(self) -> tuple[DatasetMeta, pd.DataFrame]:
        if not self.active_dataset_id or self.active_dataset_id not in self.datasets:
            raise ValueError("No active dataset is available.")
        meta = self.datasets[self.active_dataset_id]
        return meta, self.storage.load(meta)

    def requires_approval(self, tool_name: str, payload: dict[str, Any] | None = None) -> bool:
        """
        Check whether a tool call requires Human-in-the-Loop approval.
        Combines the HITL tool whitelist with the SecurityPolicy's
        dynamic needs_hitl() check (which catches prompt injection etc.).
        """
        if tool_name in self.hitl_tools:
            return True
        return self.security.needs_hitl(tool_name, payload or {})


@dataclass
class AgentResult:
    """Typed output from every specialist agent."""
    message: str
    artifacts: list[ArtifactEnvelope] = field(default_factory=list)
    datasets: dict[str, DatasetMeta] = field(default_factory=dict)
    active_dataset_id: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    degraded: bool = False
    error: str | None = None


class BaseAgent:
    """
    Protocol contract for all specialist agents.

    Every agent must implement async run(ctx, instruction) -> AgentResult.
    The supervisor routes work to agents based on the plan; agents are
    intentionally unaware of the graph topology (separation of concerns).
    """
    name = "base_agent"
    description = ""

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        raise NotImplementedError
