from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from schemas import ChatMessage


def sliding_window_messages(
    messages: list[ChatMessage],
    *,
    max_messages: int = 20,
    max_chars: int = 2_000,
) -> list[ChatMessage]:
    """Bound context and strip oversized tool payloads to limit cost/OOM risk."""
    trimmed: list[ChatMessage] = []
    for message in messages[-max_messages:]:
        content = message.content or ""
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...[truncated]..."
        trimmed.append(message.model_copy(update={"content": content}))
    return trimmed


def dataframe_profile(df: pd.DataFrame, sample_rows: int = 20) -> dict[str, Any]:
    """Extract compact dataframe metadata instead of pushing full frames to the LLM."""
    if df is None:
        return {}
    profile: dict[str, Any] = {
        "shape": [int(df.shape[0]), int(df.shape[1])],
        "columns": [str(c) for c in df.columns],
        "dtypes": {str(k): str(v) for k, v in df.dtypes.items()},
        "missing": {str(k): int(v) for k, v in df.isna().sum().items()},
    }
    try:
        profile["sample"] = df.head(sample_rows).to_dict(orient="records")
    except Exception:
        profile["sample"] = []
    return profile


def dataframe_fingerprint(df: pd.DataFrame) -> tuple[str, str]:
    schema_blob = "|".join([f"{c}:{df[c].dtype}" for c in df.columns])
    schema_hash = hashlib.sha256(schema_blob.encode("utf-8")).hexdigest()[:16]
    try:
        sample = df.head(200).to_json(orient="split", date_format="iso")
    except Exception:
        sample = schema_blob
    fingerprint = hashlib.sha256(
        f"{df.shape}:{schema_hash}:{sample}".encode("utf-8", errors="ignore")
    ).hexdigest()[:24]
    return schema_hash, fingerprint

