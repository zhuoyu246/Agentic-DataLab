from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    DEGRADED = "degraded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    role: Literal["system", "user", "assistant", "tool"] = "user"
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    agent_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceSettings(BaseModel):
    tenant_id: str = "default"
    user_id: str = "local-user"
    provider: Literal["vllm", "openai-compatible", "mock"] = "vllm"
    model: str | None = None
    api_key: str | None = None
    use_large_planner: bool = True
    use_small_react_model: bool = True
    proactive_workflow_mode: bool = True
    recursion_limit: int = Field(default=12, ge=1, le=64)
    enable_memory: bool = True
    require_human_approval: bool = True
    allow_write_sql: bool = False
    mlflow_enabled: bool = True
    h2o_enabled: bool = True


class SessionCreate(BaseModel):
    name: str | None = None
    settings: WorkspaceSettings = Field(default_factory=WorkspaceSettings)


class DatasetMeta(BaseModel):
    id: str
    label: str
    stage: str = "raw"
    tenant_id: str = "default"
    shape: tuple[int, int] = (0, 0)
    columns: list[str] = Field(default_factory=list)
    schema_hash: str | None = None
    fingerprint: str | None = None
    hot: bool = True
    uri: str | None = None
    parent_ids: list[str] = Field(default_factory=list)
    created_by: str = "system"
    created_at: datetime = Field(default_factory=utc_now)
    provenance: dict[str, Any] = Field(default_factory=dict)


class DatasetPreview(BaseModel):
    dataset_id: str
    columns: list[str]
    rows: list[dict[str, Any]]
    shape: tuple[int, int]
    profile: dict[str, Any] = Field(default_factory=dict)


class UploadResponse(BaseModel):
    dataset: DatasetMeta
    preview: DatasetPreview


class ArtifactEnvelope(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    kind: str
    title: str
    dataset_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    uri: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    degraded: bool = False
    error: str | None = None


class PipelineNode(BaseModel):
    id: str
    label: str
    stage: str
    dataset_id: str | None = None
    status: AgentRunStatus = AgentRunStatus.SUCCEEDED
    metrics: dict[str, Any] = Field(default_factory=dict)
    code: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PipelineEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None


class PipelineGraph(BaseModel):
    nodes: list[PipelineNode] = Field(default_factory=list)
    edges: list[PipelineEdge] = Field(default_factory=list)
    active_dataset_id: str | None = None
    pipeline_hash: str | None = None


class AgentEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    session_id: str
    run_id: str | None = None
    type: Literal[
        "status",
        "token",
        "agent_start",
        "agent_end",
        "artifact",
        "approval_required",
        "warning",
        "error",
        "done",
    ] = "status"
    status: AgentRunStatus | None = None
    agent_name: str | None = None
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    session_id: str
    run_id: str
    tool_name: str
    reason: str
    proposed_action: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ApprovalDecision(BaseModel):
    approval_id: str
    approved: bool
    comment: str | None = None


class ChatRequest(BaseModel):
    prompt: str
    active_dataset_id: str | None = None
    settings: WorkspaceSettings | None = None
    idempotency_key: str | None = None
    resume_approval_id: str | None = None
    stream: bool = True


class ChatResponse(BaseModel):
    session_id: str
    run_id: str
    status: AgentRunStatus
    message: ChatMessage
    artifacts: list[ArtifactEnvelope] = Field(default_factory=list)
    pipeline: PipelineGraph = Field(default_factory=PipelineGraph)
    datasets: list[DatasetMeta] = Field(default_factory=list)
    approvals: list[ApprovalRequest] = Field(default_factory=list)


class SessionState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = "Untitled Workspace"
    settings: WorkspaceSettings = Field(default_factory=WorkspaceSettings)
    messages: list[ChatMessage] = Field(default_factory=list)
    datasets: dict[str, DatasetMeta] = Field(default_factory=dict)
    artifacts: list[ArtifactEnvelope] = Field(default_factory=list)
    pending_approvals: list[ApprovalRequest] = Field(default_factory=list)
    pipeline: PipelineGraph = Field(default_factory=PipelineGraph)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ProjectSummary(BaseModel):
    id: str
    name: str
    session_id: str | None = None
    datasets_total: int = 0
    artifacts_total: int = 0
    saved_at: datetime = Field(default_factory=utc_now)
    uri: str | None = None
