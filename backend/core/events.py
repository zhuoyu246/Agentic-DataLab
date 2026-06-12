from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from typing import AsyncIterator

from schemas import AgentEvent, AgentRunStatus


class EventBus:
    """
    SSE asymmetric event bus.

    Writes are internal and high volume; reads are client-facing SSE streams.
    When a client is slow, logs are degraded instead of blocking agent execution.
    """

    def __init__(self, queue_size: int = 512, replay_size: int = 256) -> None:
        self._queues: dict[str, set[asyncio.Queue[AgentEvent]]] = defaultdict(set)
        self._replay: dict[str, deque[AgentEvent]] = defaultdict(
            lambda: deque(maxlen=replay_size)
        )
        self._queue_size = queue_size
        self._lock = asyncio.Lock()

    async def publish(self, event: AgentEvent) -> None:
        self._replay[event.session_id].append(event)
        async with self._lock:
            queues = list(self._queues.get(event.session_id, set()))
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                degraded = AgentEvent(
                    session_id=event.session_id,
                    run_id=event.run_id,
                    type="warning",
                    status=AgentRunStatus.DEGRADED,
                    message="SSE client is slow; verbose events were compacted.",
                    payload={"dropped_event_type": event.type},
                )
                try:
                    _ = queue.get_nowait()
                    queue.put_nowait(degraded)
                except Exception:
                    pass

    async def subscribe(
        self, session_id: str, last_event_id: str | None = None
    ) -> AsyncIterator[str]:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._queues[session_id].add(queue)
        try:
            replay = list(self._replay.get(session_id, []))
            if last_event_id:
                found = False
                for event in replay:
                    if found:
                        yield self._format(event)
                    elif event.id == last_event_id:
                        found = True
            else:
                for event in replay[-50:]:
                    yield self._format(event)
            while True:
                event = await queue.get()
                yield self._format(event)
                if event.type == "done":
                    await asyncio.sleep(0.05)
        finally:
            async with self._lock:
                self._queues[session_id].discard(queue)

    def recent(self, session_id: str, limit: int = 100) -> list[AgentEvent]:
        events = list(self._replay.get(session_id, []))
        return events[-limit:]

    @staticmethod
    def _format(event: AgentEvent) -> str:
        payload = event.model_dump(mode="json")
        return (
            f"id: {event.id}\n"
            f"event: {event.type}\n"
            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        )

