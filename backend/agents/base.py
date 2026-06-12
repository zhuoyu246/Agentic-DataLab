from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from core.events import EventBus
from core.security import SecurityPolicy, TenantContext
from core.storage import DatasetStorage
from schemas import AgentEvent, AgentRunStatus, ArtifactEnvelope, DatasetMeta


@dataclass
class AgentContext:
    session_id: str
    run_id: str
    tenant: TenantContext
    prompt: str
    active_dataset_id: str | None
    storage: DatasetStorage
    events: EventBus
    security: SecurityPolicy
    history: list[dict[str, str]] = field(default_factory=list)
    datasets: dict[str, DatasetMeta] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    approvals: dict[str, bool] = field(default_factory=dict)

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


@dataclass
class AgentResult:
    message: str
    artifacts: list[ArtifactEnvelope] = field(default_factory=list)
    datasets: dict[str, DatasetMeta] = field(default_factory=dict)
    active_dataset_id: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    degraded: bool = False
    error: str | None = None


class BaseAgent:
    name = "base_agent"
    description = ""

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        raise NotImplementedError

