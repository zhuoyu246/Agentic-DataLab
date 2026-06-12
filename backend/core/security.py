from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMIN = "admin"


@dataclass(slots=True)
class TenantContext:
    tenant_id: str
    user_id: str
    role: Role = Role.ANALYST


class SQLPolicyError(PermissionError):
    pass


class SecurityPolicy:
    WRITE_SQL = re.compile(
        r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge)\b",
        flags=re.IGNORECASE,
    )
    PROMPT_INJECTION = re.compile(
        r"(ignore previous|developer message|system prompt|exfiltrate|dump secrets|bypass)",
        flags=re.IGNORECASE,
    )

    def __init__(self, *, allow_write_sql: bool, sql_require_hitl: bool) -> None:
        self.allow_write_sql = allow_write_sql
        self.sql_require_hitl = sql_require_hitl

    def assert_sql_allowed(self, sql: str, *, approved: bool = False) -> None:
        if not isinstance(sql, str) or not sql.strip():
            raise SQLPolicyError("SQL is empty.")
        if self.WRITE_SQL.search(sql):
            if not self.allow_write_sql:
                raise SQLPolicyError("Write SQL is disabled by policy.")
            if self.sql_require_hitl and not approved:
                raise SQLPolicyError("Write SQL requires HITL approval.")

    def needs_hitl(self, tool_name: str, payload: dict[str, Any]) -> bool:
        text = f"{tool_name}\n{payload}"
        if tool_name in {"sql.execute", "python.exec", "mlflow.transition_model"}:
            return True
        if self.PROMPT_INJECTION.search(text):
            return True
        return False

    @staticmethod
    def tenant_predicate(ctx: TenantContext, table_alias: str = "") -> str:
        prefix = f"{table_alias}." if table_alias else ""
        tenant = ctx.tenant_id.replace("'", "''")
        return f"{prefix}tenant_id = '{tenant}'"

