from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from api.deps import workspace
from schemas import ApprovalDecision
from services.workspace import WorkspaceService

router = APIRouter(prefix="/sessions/{session_id}/approvals", tags=["approvals"])


@router.post("")
async def decide_approval(
    session_id: str,
    decision: ApprovalDecision,
    background_tasks: BackgroundTasks,
    service: WorkspaceService = Depends(workspace),
):
    try:
        result = await service.record_approval(session_id, decision)
        if decision.approved and result.get("resume_available"):
            background_tasks.add_task(
                service.resume_after_approval,
                session_id,
                decision.approval_id,
            )
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
