from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from api.deps import event_bus
from core.events import EventBus
from schemas import AgentEvent

router = APIRouter(prefix="/sessions/{session_id}/events", tags=["events"])


@router.get("")
async def stream_events(
    session_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    bus: EventBus = Depends(event_bus),
):
    return StreamingResponse(
        bus.subscribe(session_id, last_event_id=last_event_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/recent", response_model=list[AgentEvent])
async def recent_events(
    session_id: str,
    limit: int = 100,
    bus: EventBus = Depends(event_bus),
):
    return bus.recent(session_id, limit=limit)

