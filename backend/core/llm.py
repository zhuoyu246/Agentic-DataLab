from __future__ import annotations

from typing import Any
from urllib.parse import urlparse
import asyncio

import httpx
from pydantic import BaseModel

from core.config import Settings
from core.json_guard import GuardResult, JsonGuard
from schemas import ChatMessage


class VLLMClient:
    """
    OpenAI-compatible vLLM client.

    PagedAttention is configured in the vLLM serving process. This client keeps
    the application side stateless, bounded, and compatible with private models.
    """

    def __init__(self, settings: Settings, api_key: str | None = None) -> None:
        self.settings = settings
        self.api_key = api_key
        self._guard = JsonGuard()
        self._availability_cache: bool | None = None

    async def is_available(self, timeout: float = 0.5) -> bool:
        if self._availability_cache is True:
            return True
        parsed = urlparse(self.settings.vllm_base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout
            )
            writer.close()
            await writer.wait_closed()
            self._availability_cache = True
            return True
        except Exception:
            return False

    async def complete(
        self,
        messages: list[ChatMessage] | list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        normalized = [
            m.model_dump(include={"role", "content"})
            if isinstance(m, ChatMessage)
            else {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in messages
        ]
        payload = {
            "model": model or self.settings.vllm_model,
            "messages": normalized,
            "temperature": temperature,
            "max_tokens": max_tokens or self.settings.llm_max_output_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key or self.settings.vllm_api_key}"}
        async with httpx.AsyncClient(timeout=self.settings.vllm_timeout_seconds) as c:
            resp = await c.post(
                f"{self.settings.vllm_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def complete_json(
        self,
        messages: list[ChatMessage] | list[dict[str, Any]],
        schema: type[BaseModel],
        *,
        model: str | None = None,
        retries: int = 1,
    ) -> GuardResult:
        prompt = list(messages)
        for attempt in range(retries + 1):
            text = await self.complete(prompt, model=model, temperature=0.0)
            result = self._guard.validate(text, schema)
            if result.ok:
                return result
            prompt = [
                *prompt,
                {
                    "role": "user",
                    "content": (
                        "Return only valid JSON matching the schema. "
                        f"Validation error: {result.error}"
                    ),
                },
            ]
        return result
