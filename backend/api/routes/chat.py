from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from api.deps import workspace
from schemas import AgentRunStatus, ChatMessage, ChatRequest, ChatResponse
from services.workspace import WorkspaceService

router = APIRouter(prefix="/sessions/{session_id}/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    session_id: str,
    payload: ChatRequest,
    background_tasks: BackgroundTasks,
    service: WorkspaceService = Depends(workspace),
):
    try:
        session = await service.get_session(session_id)
        background_tasks.add_task(service.chat_async, session_id, payload)
        return ChatResponse(
            session_id=session_id,
            run_id=uuid4().hex,
            status=AgentRunStatus.QUEUED,
            message=ChatMessage(
                role="assistant",
                content="[supervisor] Task queued; waiting for scheduler...",
                metadata={"live": True},
            ),
            artifacts=[],
            pipeline=session.pipeline,
            datasets=list(session.datasets.values()),
            approvals=list(session.pending_approvals),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
