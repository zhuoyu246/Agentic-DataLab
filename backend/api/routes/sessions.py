from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import workspace
from schemas import SessionCreate, SessionState
from services.workspace import WorkspaceService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionState)
async def create_session(
    payload: SessionCreate, service: WorkspaceService = Depends(workspace)
):
    return await service.create_session(payload)


@router.get("/{session_id}", response_model=SessionState)
async def get_session(session_id: str, service: WorkspaceService = Depends(workspace)):
    try:
        return await service.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

