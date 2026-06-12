from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import workspace
from schemas import ApprovalDecision
from services.workspace import WorkspaceService

router = APIRouter(prefix="/sessions/{session_id}/approvals", tags=["approvals"])


@router.post("")
async def decide_approval(
    session_id: str,
    decision: ApprovalDecision,
    service: WorkspaceService = Depends(workspace),
):
    try:
        return service.record_approval(session_id, decision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

