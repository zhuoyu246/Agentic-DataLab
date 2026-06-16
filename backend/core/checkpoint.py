"""
Checkpoint Infrastructure — Tiered Storage with LangGraph Adapter.
（状态快照基建 —— 带有 LangGraph 适配器的分级存储架构）

Architecture (from interview architecture documents):
架构设计（源自面试架构文档）：
- Dev (开发环境): MemorySaver (内存存储，零配置，单进程可用)
- Prod (生产环境): Redis hot-tier (热数据层：激进的过期时间 TTL=2小时，防止遗弃会话导致内存溢出 OOM)
        + PostgreSQL cold-tier (冷数据归档层：仅当大图流转到最终 END 节点时才进行永久归档)

The create_checkpointer() factory reads CHECKPOINT_BACKEND env var and returns
the appropriate LangGraph-compatible checkpointer. This allows hot-swapping
the persistence layer without touching any business code.
（工厂模式函数 create_langgraph_checkpointer() 通过读取配置来返回适用的 Checkpointer。
这允许我们在不触碰任何底层业务代码的情况下，对状态持久化层进行“热插拔”。）
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Protocol

import orjson


# ---------------------------------------------------------------------------
# Protocol — shared interface for custom checkpointers
# ---------------------------------------------------------------------------
# 协议层：为所有自定义的 Checkpointer 定义统一的接口契约（鸭子类型）
class Checkpointer(Protocol):
    async def save(self, session_id: str, state: dict[str, Any]) -> None: ...

    async def load(self, session_id: str) -> dict[str, Any] | None: ...

    async def history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# FileCheckpointer — local fallback with time-travel snapshots
# ---------------------------------------------------------------------------
class FileCheckpointer:
    """Local fallback with time-travel snapshots.
    （本地文件回退方案：支持时间旅行快照）
    """

    def __init__(self, root: Path, ttl_seconds: int = 86_400) -> None:
        self.root = root
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, session_id: str, state: dict[str, Any]) -> None:
        now = time.time()
        folder = self.root / session_id
        folder.mkdir(parents=True, exist_ok=True)
        payload = {"saved_ts": now, "state": state}
        # 使用 orjson 替代自带的 json 库，极大提升序列化性能（特别是包含 numpy 数据时）
        blob = orjson.dumps(payload, option=orjson.OPT_SERIALIZE_NUMPY)
        (folder / "latest.json").write_bytes(blob)
        (folder / f"{int(now * 1000)}.json").write_bytes(blob)
        # 触发本地文件的自动过期清理机制
        self._prune(folder, now)

    async def load(self, session_id: str) -> dict[str, Any] | None:
        path = self.root / session_id / "latest.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data.get("state") if isinstance(data, dict) else None

    async def history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        # 获取历史快照记录，供时间旅行（Time-travel）回滚使用
        folder = self.root / session_id
        if not folder.exists():
            return []
        files = sorted(
            [p for p in folder.glob("*.json") if p.name != "latest.json"],
            key=lambda p: p.name,
            reverse=True,
        )
        out: list[dict[str, Any]] = []
        for path in files[:limit]:
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return out

    def _prune(self, folder: Path, now: float) -> None:
        # 清理超期的快照文件，防止本地磁盘被打爆
        for path in folder.glob("*.json"):
            if path.name == "latest.json":
                continue
            try:
                ts = int(path.stem) / 1000
                if now - ts > self.ttl_seconds:
                    path.unlink(missing_ok=True)
            except Exception:
                continue


# ---------------------------------------------------------------------------
# RedisCheckpointer — hot-tier with aggressive TTL (production)
# ---------------------------------------------------------------------------
class RedisCheckpointer:
    """
    Redis TTL checkpointer for distributed cluster deployments.
    （专为分布式集群部署设计的 Redis TTL 状态检查点管理器）

    Architecture rationale (架构设计原理):
    - MemorySaver is single-process; if user triggers interrupt() on Node A
      and resumes on Node B, the state is lost. Redis solves this.
      （原生 MemorySaver 是单进程的。如果用户在机器 A 触发了 HITL 审批挂起，
        随后在机器 B 审批恢复，单进程内存状态就会丢失。Redis 完美解决了跨节点状态共享问题。）
    - Aggressive TTL (default 2h) acts as automatic garbage collection,
      preventing abandoned sessions from bloating memory.
      （激进的 TTL 超时策略（默认2小时）起到了自动垃圾回收的作用，
        防止那些用户发了一半就不管的废弃对话把 Redis 昂贵的内存撑爆。）
    - History is capped at 100 entries via LTRIM.
      （通过 LTRIM 指令，强制将历史状态列表长度截断在 100 条以内，维持恒定的内存占用。）
    """

    def __init__(self, redis_url: str, ttl_seconds: int = 7_200) -> None:
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self._client = None

    async def _redis(self):
        # 懒加载 Redis 客户端
        if self._client is None:
            import redis.asyncio as redis

            self._client = redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    async def save(self, session_id: str, state: dict[str, Any]) -> None:
        r = await self._redis()
        now = int(time.time() * 1000)
        payload = json.dumps({"saved_ts": now, "state": state}, default=str)
        latest = f"checkpoint:{session_id}:latest"
        hist = f"checkpoint:{session_id}:history"
        
        # 覆写最新状态，并赋予超时时间
        await r.set(latest, payload, ex=self.ttl_seconds)
        # 将本次快照推入历史队列
        await r.lpush(hist, payload)
        # O(1) 的列表截断：只保留最近的 100 条历史状态，彻底拒绝 OOM
        await r.ltrim(hist, 0, 99)
        # 为历史队列刷新超时时间
        await r.expire(hist, self.ttl_seconds)

    async def load(self, session_id: str) -> dict[str, Any] | None:
        r = await self._redis()
        raw = await r.get(f"checkpoint:{session_id}:latest")
        if not raw:
            return None
        data = json.loads(raw)
        return data.get("state")

    async def history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        r = await self._redis()
        rows = await r.lrange(f"checkpoint:{session_id}:history", 0, limit - 1)
        return [json.loads(x) for x in rows]


# ---------------------------------------------------------------------------
# Factory — create_checkpointer()
# ---------------------------------------------------------------------------
def create_langgraph_checkpointer(backend: str = "memory", **kwargs):
    """
    Factory function to create a LangGraph-compatible checkpointer.
    （工厂模式函数：根据配置动态生成兼容 LangGraph 的状态检查点对象）

    Supports tiered storage strategy (支持多级存储架构策略):
    - "memory"   → MemorySaver (dev/test, single-process)
                   （开发/测试环境，单进程内存存储，零依赖开箱即用）
    - "redis"    → Redis with TTL (production hot-tier)
                   （生产环境热数据层：利用 Redis 的 TTL 机制做高速流转）
    - "postgres" → PostgresSaver (production cold-tier archival)
                   （生产环境冷数据层：利用 PostgreSQL 搞永久状态归档）

    Usage (使用示例):
        checkpointer = create_langgraph_checkpointer("memory")
        graph = workflow.compile(checkpointer=checkpointer)
    """
    backend = backend.lower().strip()

    if backend == "memory":
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()

    elif backend == "redis":
        # Redis 热数据层：激进的 TTL 防止因遗弃的对话导致内存溢出 (OOM)
        redis_url = kwargs.get("redis_url", "redis://localhost:6379/0")
        return RedisCheckpointer(redis_url=redis_url, ttl_seconds=kwargs.get("ttl_seconds", 7_200))

    elif backend == "postgres":
        # PostgreSQL 冷数据层：仅用于高价值对话的最终归档落盘
        # 前置要求: pip install langgraph-checkpoint-postgres psycopg[binary]
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            conn_string = kwargs.get("conn_string", "")
            if not conn_string:
                raise ValueError("PostgreSQL checkpoint requires 'conn_string' kwarg.")
            return AsyncPostgresSaver.from_conn_string(conn_string)
        except ImportError:
            raise ImportError(
                "PostgresSaver requires: pip install langgraph-checkpoint-postgres psycopg[binary]"
            )

    else:
        raise ValueError(f"Unknown checkpoint backend: {backend!r}. Use 'memory', 'redis', or 'postgres'.")
