from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import workspace
from schemas import ProjectSummary, SessionState
from services.workspace import WorkspaceService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummary])
async def list_projects(service: WorkspaceService = Depends(workspace)):
    return service.list_projects()


@router.post("/sessions/{session_id}", response_model=ProjectSummary)
async def save_project(
    session_id: str,
    name: str | None = None,
    service: WorkspaceService = Depends(workspace),
):
    try:
        return await service.save_project(session_id, name=name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/load", response_model=SessionState)
async def load_project(project_id: str, service: WorkspaceService = Depends(workspace)):
    try:
        return service.load_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

