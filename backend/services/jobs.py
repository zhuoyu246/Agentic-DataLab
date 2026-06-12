from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import uuid4

from schemas import AgentRunStatus


JobCallable = Callable[[], Awaitable[dict[str, Any]]]


@dataclass
class JobState:
    id: str
    kind: str
    status: AgentRunStatus = AgentRunStatus.QUEUED
    result: dict[str, Any] | None = None
    error: str | None = None
    webhook_url: str | None = None
    polls: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class JobManager:
    """Async non-blocking state machine for H2O/AutoML and other long jobs."""

    def __init__(self) -> None:
        self.jobs: dict[str, JobState] = {}

    def submit(
        self,
        kind: str,
        coro_factory: JobCallable,
        *,
        webhook_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobState:
        job = JobState(
            id=uuid4().hex,
            kind=kind,
            webhook_url=webhook_url,
            metadata=metadata or {},
        )
        self.jobs[job.id] = job
        asyncio.create_task(self._runner(job, coro_factory))
        return job

    def get(self, job_id: str) -> JobState:
        return self.jobs[job_id]

    async def _runner(self, job: JobState, coro_factory: JobCallable) -> None:
        job.status = AgentRunStatus.RUNNING
        try:
            job.result = await coro_factory()
            job.status = AgentRunStatus.SUCCEEDED
        except Exception as exc:
            job.error = str(exc)
            job.status = AgentRunStatus.FAILED

