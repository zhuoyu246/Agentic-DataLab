from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from core.config import get_settings


settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password strength according to security policy.

    Requirements:
    - Minimum 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 12:
        return False, "Password must be at least 12 characters long"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"

    # Check for common weak passwords
    weak_passwords = [
        "password123!",
        "password1234",
        "admin123456",
        "welcome12345",
        "qwerty123456",
        "123456qwerty",
    ]
    if password.lower() in weak_passwords:
        return False, "Password is too common"

    return True, ""


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None
