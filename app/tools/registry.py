"""Tool reyestri — agentə açıq tool-ları saxlayır.

İstifadə (gələcək fazalarda):
    from app.tools.registry import tools
    tools.register(SaveNoteTool(...))
    schemas = tools.schemas()          # Claude API-yə ötürülür
    tool = tools.get("save_note")
    result = await tool.run(**args)
"""

from __future__ import annotations

from typing import Any

from app.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool qeydiyyatdan keçməyib: {name!r}")
        return self._tools[name]

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [t.to_anthropic_schema() for t in self._tools.values()]


tools = ToolRegistry()
