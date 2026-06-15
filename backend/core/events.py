from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from typing import AsyncIterator

from schemas import AgentEvent, AgentRunStatus


class EventBus:
    """
    SSE asymmetric event bus.
    （基于 SSE 非对称通信模式的全局事件总线）

    Architecture rationale (架构设计原理):
    - Writes are internal and high volume; reads are client-facing SSE streams.
      （内部写入是高频的，而读取端是面向前端 Web 客户端的 SSE 流。）
    - When a client is slow, logs are degraded instead of blocking agent execution.
      （防火墙隔离/降级防御机制：如果前端网络卡顿导致消费变慢，直接抛弃冗余日志并降级，
        绝对不允许前端的慢速读取阻塞后端高昂的大模型推理进程。）
    """

    def __init__(self, queue_size: int = 512, replay_size: int = 256) -> None:
        self._queues: dict[str, set[asyncio.Queue[AgentEvent]]] = defaultdict(set)
        # Replay 缓冲区：为断线重连（如网络抖动）提供历史消息重播补偿
        self._replay: dict[str, deque[AgentEvent]] = defaultdict(
            lambda: deque(maxlen=replay_size)
        )
        self._queue_size = queue_size
        self._lock = asyncio.Lock()

    async def publish(self, event: AgentEvent) -> None:
        self._replay[event.session_id].append(event)
        async with self._lock:
            queues = list(self._queues.get(event.session_id, set()))
        for queue in queues:
            try:
                # 尝试无阻塞推送
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # 核心降级逻辑 (Graceful Degradation)：
                # 当队列满时（代表前端来不及接收），丢弃旧的冗余日志，塞入一条降级警告，
                # 从而保证内存不爆，且绝不阻塞 Agent 的继续运行。
                degraded = AgentEvent(
                    session_id=event.session_id,
                    run_id=event.run_id,
                    type="warning",
                    status=AgentRunStatus.DEGRADED,
                    message="SSE client is slow; verbose events were compacted.",
                    payload={"dropped_event_type": event.type},
                )
                try:
                    _ = queue.get_nowait()  # 强行抛弃队头旧消息
                    queue.put_nowait(degraded)
                except Exception:
                    pass

    async def subscribe(
        self, session_id: str, last_event_id: str | None = None
    ) -> AsyncIterator[str]:
        # 创建客户端专属消费队列
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._queues[session_id].add(queue)
        try:
            replay = list(self._replay.get(session_id, []))
            # 断点续传补偿机制：根据前端传来的 last_event_id 无缝接续事件流
            if last_event_id:
                found = False
                for event in replay:
                    if found:
                        yield self._format(event)
                    elif event.id == last_event_id:
                        found = True
            else:
                # 初次连接，推送最近的历史快照
                for event in replay[-50:]:
                    yield self._format(event)
            
            # 进入实时挂起监听状态
            while True:
                event = await queue.get()
                yield self._format(event)
                if event.type == "done":
                    await asyncio.sleep(0.05)
        finally:
            # 客户端断开连接（如关掉浏览器），自动释放队列资源防内存泄漏
            async with self._lock:
                self._queues[session_id].discard(queue)

    def recent(self, session_id: str, limit: int = 100) -> list[AgentEvent]:
        events = list(self._replay.get(session_id, []))
        return events[-limit:]

    @staticmethod
    def _format(event: AgentEvent) -> str:
        # 将对象格式化为 W3C 标准的 Server-Sent Events (SSE) 协议报文
        payload = event.model_dump(mode="json")
        return (
            f"id: {event.id}\n"
            f"event: {event.type}\n"
            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        )

