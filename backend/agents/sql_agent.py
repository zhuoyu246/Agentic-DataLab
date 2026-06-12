from __future__ import annotations

import re
import hashlib

import pandas as pd
import sqlalchemy as sa

from agents.base import AgentContext, AgentResult, BaseAgent
from core.security import SQLPolicyError
from schemas import AgentEvent, AgentRunStatus, ApprovalRequest, ArtifactEnvelope


class SQLAgent(BaseAgent):
    name = "sql_agent"
    description = "Guarded SQL execution with RLS and HITL enforcement."

    def __init__(self, default_url: str = "sqlite:///:memory:") -> None:
        self.default_url = default_url

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        sql_text = self._extract_sql(instruction)
        if not sql_text:
            return AgentResult(message="No SQL statement found.", degraded=True)
        approved = ctx.approvals.get(self._approval_key(sql_text), False)
        try:
            ctx.security.assert_sql_allowed(sql_text, approved=approved)
        except SQLPolicyError as exc:
            approval = ApprovalRequest(
                session_id=ctx.session_id,
                run_id=ctx.run_id,
                tool_name="sql.execute",
                reason=str(exc),
                proposed_action={"sql": sql_text},
            )
            await ctx.events.publish(
                AgentEvent(
                    session_id=ctx.session_id,
                    run_id=ctx.run_id,
                    type="approval_required",
                    status=AgentRunStatus.WAITING_APPROVAL,
                    agent_name=self.name,
                    message=str(exc),
                    payload=approval.model_dump(mode="json"),
                )
            )
            return AgentResult(
                message=f"SQL requires approval: {exc}",
                degraded=True,
                artifacts=[
                    ArtifactEnvelope(
                        kind="approval_required",
                        title="SQL approval required",
                        payload=approval.model_dump(mode="json"),
                    )
                ],
            )
        await ctx.emit("Executing guarded SQL.", agent_name=self.name)
        db_url = ctx.settings.get("sql_url") or self.default_url
        engine = sa.create_engine(db_url)
        with engine.connect() as conn:
            df = pd.read_sql(sa.text(sql_text), conn)
        meta = ctx.storage.register(
            df,
            tenant_id=ctx.tenant.tenant_id,
            label="sql result",
            stage="sql",
            created_by=self.name,
            provenance={"source_type": "sql", "query": sql_text, "db_url": db_url},
        )
        return AgentResult(
            message=f"SQL returned {df.shape[0]} rows and {df.shape[1]} columns.",
            datasets={meta.id: meta},
            active_dataset_id=meta.id,
            artifacts=[
                ArtifactEnvelope(
                    kind="sql_result",
                    title="SQL result",
                    dataset_id=meta.id,
                    payload={"query": sql_text, "shape": meta.shape},
                )
            ],
        )

    @staticmethod
    def _extract_sql(text: str) -> str | None:
        fenced = re.search(r"```sql\s*(.*?)```", text, flags=re.I | re.S)
        if fenced:
            return fenced.group(1).strip()
        m = re.search(r"\b(select|with)\b.+", text, flags=re.I | re.S)
        return m.group(0).strip().rstrip(";") if m else None

    @staticmethod
    def _approval_key(sql_text: str) -> str:
        digest = hashlib.sha256(sql_text.encode("utf-8", errors="ignore")).hexdigest()
        return f"sql:{digest}"
