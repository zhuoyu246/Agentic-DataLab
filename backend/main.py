from __future__ import annotations

from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.routes import approvals, auth, chat, datasets, events, health, projects, sessions
from api.middleware.error_handler import register_exception_handlers
from api.middleware.rate_limit import register_rate_limiter
from core.config import get_settings
from core.events import EventBus
from core.metrics import http_request_duration_seconds, http_requests_total
from services.workspace import WorkspaceService
from prometheus_client import make_asgi_app


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

    # Register global exception handlers
    register_exception_handlers(app)

    # Register rate limiter
    register_rate_limiter(app)

    @app.middleware("http")
    async def record_http_metrics(request: Request, call_next):
        started_at = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            endpoint = getattr(route, "path", request.url.path)
            http_requests_total.labels(
                method=request.method,
                endpoint=endpoint,
                status=str(status_code),
            ).inc()
            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=endpoint,
            ).observe(perf_counter() - started_at)

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
    app.include_router(auth.router, prefix=prefix)
    app.include_router(health.router, prefix=prefix)
    app.include_router(sessions.router, prefix=prefix)
    app.include_router(datasets.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)
    app.include_router(events.router, prefix=prefix)
    app.include_router(projects.router, prefix=prefix)
    app.include_router(approvals.router, prefix=prefix)

    # Mount Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    return app


app = create_app()
