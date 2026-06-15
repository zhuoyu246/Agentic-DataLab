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
    """
    上下文截断与滑动窗口机制 (Sliding Window & Context Truncation)
    架构意义：
    1. 限制消息条数 (max_messages)：保证历史记忆的 O(1) 常数级长度，防止长对话导致 Token 爆炸。
    2. 字符级斩首 (max_chars)：防止大模型或工具输出了极长的数据（如十万字日志），导致下游解析崩溃。
    """
    trimmed: list[ChatMessage] = []
    # 仅取最后 max_messages 条历史记录（滑动窗口）
    for message in messages[-max_messages:]:
        content = message.content or ""
        # 粗暴截断：超过限制长度直接斩首并追加提示，节省高昂的算力成本
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...[truncated]..."
        trimmed.append(message.model_copy(update={"content": content}))
    return trimmed


def dataframe_profile(df: pd.DataFrame, sample_rows: int = 20) -> dict[str, Any]:
    """
    DataFrame 轮廓提取器 (Data Profiling for LLM)
    架构意义：
    大模型无法也无必要阅读百万行的数据表。此方法仅提取宏观元数据（行列数、缺失值、列类型）
    以及少量样本数据，以最小的 Token 消耗向大模型描述当前数据的物理状态。
    """
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
    """
    DataFrame 指纹生成器 (Idempotency Hash Fingerprinting)
    架构意义：
    通过对表的 Schema 和部分数据生成哈希指纹，可以极速判断数据是否发生了实质性变更。
    这在多智能体系统中用于避免重复清洗、避免重复提取特征等幂等性（Idempotent）操作。
    """
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

