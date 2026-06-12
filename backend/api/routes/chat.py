from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from api.deps import workspace
from schemas import ChatRequest, ChatResponse, ChatMessage, AgentRunStatus, PipelineGraph
from services.workspace import WorkspaceService
from uuid import uuid4

router = APIRouter(prefix="/sessions/{session_id}/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    session_id: str,
    payload: ChatRequest,
    background_tasks: BackgroundTasks,
    service: WorkspaceService = Depends(workspace),
):
    try:
        background_tasks.add_task(service.chat_async, session_id, payload)
        return ChatResponse(
            session_id=session_id,
            run_id=uuid4().hex,
            status=AgentRunStatus.QUEUED,
            message=ChatMessage(role="assistant", content="[supervisor] 已提交任务，等待调度...", metadata={"live": True}),
            artifacts=[],
            pipeline=PipelineGraph(),
            datasets=[]
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

