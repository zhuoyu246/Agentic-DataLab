from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Protocol

import orjson


class Checkpointer(Protocol):
    async def save(self, session_id: str, state: dict[str, Any]) -> None: ...

    async def load(self, session_id: str) -> dict[str, Any] | None: ...

    async def history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]: ...


class FileCheckpointer:
    """Local fallback with time-travel snapshots."""

    def __init__(self, root: Path, ttl_seconds: int = 86_400) -> None:
        self.root = root
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, session_id: str, state: dict[str, Any]) -> None:
        now = time.time()
        folder = self.root / session_id
        folder.mkdir(parents=True, exist_ok=True)
        payload = {"saved_ts": now, "state": state}
        blob = orjson.dumps(payload, option=orjson.OPT_SERIALIZE_NUMPY)
        (folder / "latest.json").write_bytes(blob)
        (folder / f"{int(now * 1000)}.json").write_bytes(blob)
        self._prune(folder, now)

    async def load(self, session_id: str) -> dict[str, Any] | None:
        path = self.root / session_id / "latest.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("state") if isinstance(data, dict) else None

    async def history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
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
        for path in folder.glob("*.json"):
            if path.name == "latest.json":
                continue
            try:
                ts = int(path.stem) / 1000
                if now - ts > self.ttl_seconds:
                    path.unlink(missing_ok=True)
            except Exception:
                continue


class RedisCheckpointer:
    """Redis TTL checkpointer. Falls back should be wired by caller."""

    def __init__(self, redis_url: str, ttl_seconds: int = 86_400) -> None:
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self._client = None

    async def _redis(self):
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
        await r.set(latest, payload, ex=self.ttl_seconds)
        await r.lpush(hist, payload)
        await r.ltrim(hist, 0, 99)
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

