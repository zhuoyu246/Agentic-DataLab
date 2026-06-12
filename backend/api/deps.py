from __future__ import annotations

from fastapi import Request

from core.events import EventBus
from services.workspace import WorkspaceService


def workspace(request: Request) -> WorkspaceService:
    return request.app.state.workspace


def event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus

