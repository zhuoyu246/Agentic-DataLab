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
    ApprovalRequest,
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
        self.pending_approvals: dict[str, dict[str, object]] = {}
        self.approvals: dict[str, dict[str, bool]] = {}
        self.llm = VLLMClient(settings)
        self._ensure_mlflow_schema()

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
            llm = VLLMClient(self.settings, api_key=settings.api_key)
            if request.resume_approval_id:
                await self.events.emit(
                    session_id=session.id,
                    run_id=run_id,
                    type="status",
                    status=AgentRunStatus.RUNNING,
                    agent_name="supervisor",
                    message=f"Resuming approved workflow {request.resume_approval_id}.",
                )
            else:
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
                PlannerAgent(llm),
                max_steps=self.settings.max_agent_steps,
                max_reflexion_steps=self.settings.max_reflexion_steps,
            )
            result = await supervisor.run(ctx)
            self._index_pending_approvals(session, result.artifacts, request)
            session.datasets.update(result.datasets)
            if result.active_dataset_id:
                active_dataset_id = result.active_dataset_id
            session.artifacts.extend(result.artifacts)
            session.pipeline = build_pipeline_graph(session.datasets, active_dataset_id, session.artifacts)
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
            status = result.status or (
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
                approvals=list(session.pending_approvals),
            )

    async def chat_async(self, session_id: str, request: ChatRequest):
        try:
            result = await self.chat(session_id, request)
            done_message = (
                "Workflow completed successfully."
                if result.status == AgentRunStatus.SUCCEEDED
                else f"Workflow completed with status: {result.status.value}."
            )
            await self.events.emit(
                session_id=session_id,
                run_id=result.run_id,
                type="done",
                status=result.status,
                message=done_message,
                payload={"status": result.status.value}
            )
        except Exception as exc:
            import traceback
            traceback.print_exc()
            await self.events.emit(
                session_id=session_id,
                run_id=None,
                type="error",
                status=AgentRunStatus.FAILED,
                message=f"Workflow failed: {exc}",
                payload={"error": str(exc)}
            )
            await self.events.emit(
                session_id=session_id,
                run_id=None,
                type="done",
                status=AgentRunStatus.FAILED,
                message="Workflow completed with errors.",
                payload={"status": "failed"}
            )

    async def record_approval(self, session_id: str, decision: ApprovalDecision) -> dict[str, str | bool]:
        await self.get_session(session_id)
        pending = self._find_pending_approval(session_id, decision.approval_id)
        if pending is None:
            raise KeyError(f"Approval not found: {decision.approval_id}")
        approval_key = str(pending["approval_key"])
        self.approvals.setdefault(session_id, {})[approval_key] = decision.approved

        session = await self.get_session(session_id)
        if not decision.approved:
            session.pending_approvals = [
                item for item in session.pending_approvals if item.id != decision.approval_id
            ]
        session.updated_at = utc_now()
        self.sessions[session.id] = session
        await self.checkpoints.save(session.id, session.model_dump(mode="json"))

        await self.events.emit(
            session_id=session_id,
            run_id=str(pending.get("run_id") or "") or None,
            type="status",
            status=AgentRunStatus.RUNNING if decision.approved else AgentRunStatus.CANCELLED,
            agent_name="hitl",
            message=(
                f"Approval {decision.approval_id} accepted; resuming workflow."
                if decision.approved
                else f"Approval {decision.approval_id} rejected."
            ),
            payload={"approval_id": decision.approval_id, "approved": decision.approved},
        )

        if not decision.approved:
            session.messages.append(
                ChatMessage(
                    role="assistant",
                    content=f"Approval rejected: {decision.comment or 'No comment provided.'}",
                    agent_name="hitl",
                    metadata={"approval_id": decision.approval_id, "approved": False},
                )
            )
            session.updated_at = utc_now()
            self.sessions[session.id] = session
            await self.checkpoints.save(session.id, session.model_dump(mode="json"))
            self.pending_approvals.pop(decision.approval_id, None)

        return {
            "approval_id": decision.approval_id,
            "approved": decision.approved,
            "approval_key": approval_key,
            "resume_available": bool(decision.approved and pending.get("request")),
        }

    async def resume_after_approval(self, session_id: str, approval_id: str) -> None:
        pending = self._find_pending_approval(session_id, approval_id)
        if not pending or not pending.get("request"):
            return
        request = ChatRequest.model_validate(pending["request"])
        request = request.model_copy(
            update={
                "idempotency_key": f"{approval_id}:resume",
                "resume_approval_id": approval_id,
            }
        )
        try:
            await self.chat_async(session_id, request)
        finally:
            self.pending_approvals.pop(approval_id, None)
            try:
                session = await self.get_session(session_id)
            except KeyError:
                return
            session.pending_approvals = [
                item for item in session.pending_approvals if item.id != approval_id
            ]
            session.updated_at = utc_now()
            self.sessions[session.id] = session
            await self.checkpoints.save(session.id, session.model_dump(mode="json"))

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

    def _ensure_mlflow_schema(self) -> None:
        uri = self.settings.mlflow_tracking_uri
        if not uri or not uri.startswith("sqlite:///"):
            return
        db_path = self._mlflow_sqlite_path(uri)
        marker = db_path.with_suffix(f"{db_path.suffix}.schema.ok")
        try:
            if db_path.exists() and marker.exists() and marker.stat().st_mtime >= db_path.stat().st_mtime:
                return
        except OSError:
            pass

        import threading

        thread = threading.Thread(
            target=self._run_mlflow_schema_upgrade,
            args=(uri, marker),
            daemon=True,
        )
        thread.start()

    @staticmethod
    def _mlflow_sqlite_path(uri: str) -> Path:
        raw = uri.removeprefix("sqlite:///")
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _run_mlflow_schema_upgrade(uri: str, marker: Path) -> None:
        try:
            import subprocess
            import sys

            completed = subprocess.run(
                [sys.executable, "-m", "mlflow", "db", "upgrade", uri],
                cwd=str(Path.cwd()),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                check=False,
            )
            if completed.returncode == 0:
                marker.touch(exist_ok=True)
        except Exception:
            # MLflow logging is already treated as optional/degraded by agents.
            pass

    def _index_pending_approvals(
        self,
        session: SessionState,
        artifacts: list[ArtifactEnvelope],
        request: ChatRequest,
    ) -> None:
        for artifact in artifacts:
            if artifact.kind != "approval_required":
                continue
            payload = artifact.payload or {}
            try:
                approval = ApprovalRequest.model_validate(payload)
            except Exception:
                continue
            proposed = approval.proposed_action or {}
            approval_key = proposed.get("approval_key")
            sql = proposed.get("sql")
            if not isinstance(approval_key, str) and isinstance(sql, str):
                digest = hashlib.sha256(sql.encode("utf-8", errors="ignore")).hexdigest()
                approval_key = f"sql:{digest}"
                proposed["approval_key"] = approval_key
                approval = approval.model_copy(update={"proposed_action": proposed})
                artifact.payload = approval.model_dump(mode="json")
            if not isinstance(approval_key, str):
                continue

            resume_request = request.model_dump(mode="json")
            resume_request["resume_approval_id"] = approval.id
            proposed["resume_request"] = resume_request
            approval = approval.model_copy(update={"proposed_action": proposed})
            artifact.payload = approval.model_dump(mode="json")
            self.pending_approvals[approval.id] = {
                "session_id": session.id,
                "run_id": approval.run_id,
                "approval_key": approval_key,
                "request": resume_request,
            }
            if not any(item.id == approval.id for item in session.pending_approvals):
                session.pending_approvals.append(approval)

    def _find_pending_approval(
        self, session_id: str, approval_id: str
    ) -> dict[str, object] | None:
        pending = self.pending_approvals.get(approval_id)
        if pending and pending.get("session_id") == session_id:
            return pending
        session = self.sessions.get(session_id)
        if not session:
            return None
        for approval in session.pending_approvals:
            if approval.id != approval_id:
                continue
            proposed = approval.proposed_action or {}
            approval_key = proposed.get("approval_key")
            if not isinstance(approval_key, str):
                return None
            restored = {
                "session_id": session_id,
                "run_id": approval.run_id,
                "approval_key": approval_key,
                "request": proposed.get("resume_request"),
            }
            self.pending_approvals[approval_id] = restored
            return restored
        return None
