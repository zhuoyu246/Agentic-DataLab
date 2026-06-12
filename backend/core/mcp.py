from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


MCPHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class MCPToolDescriptor:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: MCPHandler | None = None
    tags: list[str] = field(default_factory=list)


class MCPRegistry:
    """Forward-compatible internal registry for later MCP server exposure."""

    def __init__(self) -> None:
        self._tools: dict[str, MCPToolDescriptor] = {}

    def register(self, tool: MCPToolDescriptor) -> None:
        self._tools[tool.name] = tool

    def list_tools(self) -> list[MCPToolDescriptor]:
        return list(self._tools.values())

    async def call(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None or tool.handler is None:
            raise KeyError(f"MCP tool not registered: {name}")
        return await tool.handler(payload)

