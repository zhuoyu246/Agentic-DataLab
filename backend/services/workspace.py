from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import hashlib

import pandas as pd
from fastapi import UploadFile

from agents import AgentContext, AgentSupervisor, PlannerAgent
from core.checkpoint import FileCheckpointer
from core.config import Settings
from core.events import EventBus
from core.idempotency import IdempotencyLockRegistry
from core.llm import VLLMClient
from core.security import Role, SecurityPolicy, TenantContext
from core.storage import DatasetStorage
from schemas import (
    AgentRunStatus,
    ArtifactEnvelope,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    DatasetMeta,
    ApprovalDecision,
    SessionCreate,
    SessionState,
    UploadResponse,
)
from schemas.domain import utc_now
from services.pipeline import build_pipeline_graph
from services.project_store import ProjectStore


class WorkspaceService:
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self.settings = settings
        self.events = event_bus
        self.storage = DatasetStorage(
            settings.data_root,
            hot_max_mb=settings.hot_dataset_max_mb,
            fmt=settings.cold_dataset_format,
        )
        self.projects = ProjectStore(settings.data_root / "projects")
        self.checkpoints = FileCheckpointer(
            settings.data_root / "checkpoints",
            ttl_seconds=settings.checkpoint_ttl_seconds,
        )
        self.idempotency = IdempotencyLockRegistry()
        self.sessions: dict[str, SessionState] = {}
        self.pending_approvals: dict[str, dict[str, str]] = {}
        self.approvals: dict[str, dict[str, bool]] = {}
        self.llm = VLLMClient(settings)

    async def create_session(self, payload: SessionCreate) -> SessionState:
        session = SessionState(
            name=payload.name or "Agentic DataLab Workspace",
            settings=payload.settings,
            messages=[
                ChatMessage(
                    role="assistant",
                    content="DataLab ready. Upload data or ask a data-science question.",
                )
            ],
        )
        self.sessions[session.id] = session
        await self.checkpoints.save(session.id, session.model_dump(mode="json"))
        return session

    async def get_session(self, session_id: str) -> SessionState:
        session = self.sessions.get(session_id)
        if session:
            return session
        data = await self.checkpoints.load(session_id)
        if data:
            session = SessionState.model_validate(data)
            self.sessions[session.id] = session
            return session
        raise KeyError(f"Session not found: {session_id}")

    async def upload_dataset(
        self,
        session_id: str,
        upload: UploadFile,
        *,
        stage: str = "raw",
    ) -> UploadResponse:
        session = await self.get_session(session_id)
        suffix = Path(upload.filename or "upload.csv").suffix.lower()
        temp_dir = self.settings.data_root / "uploads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{uuid4().hex}_{upload.filename or 'upload'}"
        temp_path.write_bytes(await upload.read())
        if suffix in {".csv", ".txt"}:
            df = pd.read_csv(temp_path)
        elif suffix in {".xlsx", ".xls"}:
            df = pd.read_excel(temp_path)
        elif suffix == ".parquet":
            df = pd.read_parquet(temp_path)
        else:
            raise ValueError(f"Unsupported upload type: {suffix}")
        meta = self.storage.register(
            df,
            tenant_id=session.settings.tenant_id,
            label=upload.filename or "uploaded dataset",
            stage=stage,
            created_by=session.settings.user_id,
            provenance={"source_type": "upload", "source": str(temp_path)},
        )
        session.datasets[meta.id] = meta
        session.pipeline = build_pipeline_graph(session.datasets, meta.id)
        session.updated_at = utc_now()
        self.sessions[session.id] = session
        await self.checkpoints.save(session.id, session.model_dump(mode="json"))
        return UploadResponse(dataset=meta, preview=self.storage.preview(meta))

    async def chat(self, session_id: str, request: ChatRequest) -> ChatResponse:
        session = await self.get_session(session_id)
        run_id = uuid4().hex
        idempotency_key = request.idempotency_key or f"{session_id}:{request.prompt}"
        async with self.idempotency.acquire(idempotency_key):
            settings = request.settings or session.settings
            session.settings = settings
            user_message = ChatMessage(role="user", content=request.prompt)
            session.messages.append(user_message)
            active_dataset_id = request.active_dataset_id or session.pipeline.active_dataset_id
            ctx = AgentContext(
                session_id=session.id,
                run_id=run_id,
                tenant=TenantContext(
                    tenant_id=settings.tenant_id,
                    user_id=settings.user_id,
                    role=Role.ANALYST,
                ),
                prompt=request.prompt,
                history=[{"role": m.role, "content": m.content} for m in session.messages[:-1]],
                datasets=dict(session.datasets),
                active_dataset_id=active_dataset_id,
                storage=self.storage,
                events=self.events,
                security=SecurityPolicy(
                    allow_write_sql=settings.allow_write_sql,
                    sql_require_hitl=settings.require_human_approval,
                ),
                approvals=self.approvals.get(session.id, {}),
                settings={
                    **settings.model_dump(),
                    "mlflow_tracking_uri": self.settings.mlflow_tracking_uri,
                    "mlflow_experiment_name": self.settings.mlflow_experiment_name,
                    "mlflow_artifact_root": self.settings.mlflow_artifact_root,
                    "h2o_max_runtime_seconds": self.settings.h2o_max_runtime_seconds,
                    "h2o_outer_timeout_seconds": self.settings.h2o_outer_timeout_seconds,
                    "h2o_max_models": self.settings.h2o_max_models,
                },
            )
            supervisor = AgentSupervisor(
                PlannerAgent(self.llm),
                max_steps=self.settings.max_agent_steps,
                max_reflexion_steps=self.settings.max_reflexion_steps,
            )
            result = await supervisor.run(ctx)
            self._index_pending_approvals(session.id, result.artifacts)
            session.datasets.update(result.datasets)
            if result.active_dataset_id:
                active_dataset_id = result.active_dataset_id
            session.artifacts.extend(result.artifacts)
            session.pipeline = build_pipeline_graph(session.datasets, active_dataset_id)
            assistant = ChatMessage(
                role="assistant",
                content=result.message,
                agent_name="supervisor",
                metadata={"run_id": run_id, "degraded": result.degraded},
            )
            session.messages.append(assistant)
            session.updated_at = utc_now()
            self.sessions[session.id] = session
            await self.checkpoints.save(session.id, session.model_dump(mode="json"))
            status = (
                AgentRunStatus.DEGRADED
                if result.degraded or result.error
                else AgentRunStatus.SUCCEEDED
            )
            return ChatResponse(
                session_id=session.id,
                run_id=run_id,
                status=status,
                message=assistant,
                artifacts=result.artifacts,
                pipeline=session.pipeline,
                datasets=list(session.datasets.values()),
            )

    async def chat_async(self, session_id: str, request: ChatRequest):
        try:
            result = await self.chat(session_id, request)
            await self.events.emit(
                session_id=session_id,
                run_id=result.run_id,
                type="done",
                message="Workflow completed successfully.",
                payload={"status": result.status.value}
            )
        except Exception as exc:
            import traceback
            traceback.print_exc()
            await self.events.emit(
                session_id=session_id,
                run_id=None,
                type="error",
                message=f"Workflow failed: {exc}",
                payload={"error": str(exc)}
            )
            await self.events.emit(
                session_id=session_id,
                run_id=None,
                type="done",
                message="Workflow completed with errors.",
                payload={"status": "failed"}
            )

    def record_approval(self, session_id: str, decision: ApprovalDecision) -> dict[str, str | bool]:
        pending = self.pending_approvals.get(decision.approval_id)
        if pending is None or pending.get("session_id") != session_id:
            raise KeyError(f"Approval not found: {decision.approval_id}")
        self.approvals.setdefault(session_id, {})[pending["approval_key"]] = decision.approved
        return {
            "approval_id": decision.approval_id,
            "approved": decision.approved,
            "approval_key": pending["approval_key"],
        }

    async def dataset_preview(
        self, session_id: str, dataset_id: str, rows: int = 50
    ):
        session = await self.get_session(session_id)
        meta = session.datasets[dataset_id]
        return self.storage.preview(meta, rows=rows)

    async def save_project(self, session_id: str, name: str | None = None):
        session = await self.get_session(session_id)
        return self.projects.save(session, name=name)

    def list_projects(self):
        return self.projects.list()

    def load_project(self, project_id: str) -> SessionState:
        session = self.projects.load(project_id)
        self.sessions[session.id] = session
        return session

    def _index_pending_approvals(
        self, session_id: str, artifacts: list[ArtifactEnvelope]
    ) -> None:
        for artifact in artifacts:
            if artifact.kind != "approval_required":
                continue
            payload = artifact.payload or {}
            approval_id = payload.get("id")
            sql = (payload.get("proposed_action") or {}).get("sql")
            if isinstance(approval_id, str) and isinstance(sql, str):
                digest = hashlib.sha256(sql.encode("utf-8", errors="ignore")).hexdigest()
                self.pending_approvals[approval_id] = {
                    "session_id": session_id,
                    "approval_key": f"sql:{digest}",
                }
