from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import workspace
from schemas import DatasetPreview, UploadResponse
from services.workspace import WorkspaceService

router = APIRouter(prefix="/sessions/{session_id}/datasets", tags=["datasets"])


@router.post("/upload", response_model=UploadResponse)
async def upload_dataset(
    session_id: str,
    file: UploadFile = File(...),
    service: WorkspaceService = Depends(workspace),
):
    try:
        return await service.upload_dataset(session_id, file)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/preview", response_model=DatasetPreview)
async def preview_dataset(
    session_id: str,
    dataset_id: str,
    rows: int = 50,
    service: WorkspaceService = Depends(workspace),
):
    try:
        return await service.dataset_preview(session_id, dataset_id, rows=rows)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

