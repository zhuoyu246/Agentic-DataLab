from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass


@dataclass
class LockRecord:
    lock: asyncio.Lock
    expires_at: float


class IdempotencyLockRegistry:
    """Per-session async locks with TTL cleanup to prevent double-click duplicate runs."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl = ttl_seconds
        self._locks: dict[str, LockRecord] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, key: str):
        lock = await self._get_lock(key)
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()

    async def _get_lock(self, key: str) -> asyncio.Lock:
        now = time.time()
        async with self._guard:
            for stale_key in [
                k for k, rec in self._locks.items() if rec.expires_at < now
            ]:
                self._locks.pop(stale_key, None)
            rec = self._locks.get(key)
            if rec is None:
                rec = LockRecord(lock=asyncio.Lock(), expires_at=now + self._ttl)
                self._locks[key] = rec
            else:
                rec.expires_at = now + self._ttl
            return rec.lock

