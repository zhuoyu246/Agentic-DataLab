from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import approvals, chat, datasets, events, health, projects, sessions
from core.config import get_settings
from core.events import EventBus
from services.workspace import WorkspaceService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    event_bus = EventBus()
    app.state.settings = settings
    app.state.event_bus = event_bus
    app.state.workspace = WorkspaceService(settings, event_bus)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Agentic DataLab",
        version="0.1.0",
        description="Enterprise private multi-agent data-science platform.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "service": "Agentic DataLab API",
            "status": "running",
            "frontend": "http://127.0.0.1:5173",
            "docs": "/docs",
            "health": f"{settings.api_prefix}/health",
            "api_prefix": settings.api_prefix,
        }

    @app.get(settings.api_prefix, include_in_schema=False)
    async def api_root():
        return {
            "service": "Agentic DataLab API",
            "routes": {
                "health": f"{settings.api_prefix}/health",
                "sessions": f"{settings.api_prefix}/sessions",
                "projects": f"{settings.api_prefix}/projects",
                "docs": "/docs",
            },
        }

    prefix = settings.api_prefix
    app.include_router(health.router, prefix=prefix)
    app.include_router(sessions.router, prefix=prefix)
    app.include_router(datasets.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)
    app.include_router(events.router, prefix=prefix)
    app.include_router(projects.router, prefix=prefix)
    app.include_router(approvals.router, prefix=prefix)
    return app


app = create_app()
