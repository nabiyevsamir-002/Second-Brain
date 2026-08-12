"""Tool interfeysi — Claude function-calling üçün.

Hər tool: name, description, input_schema (JSON schema) və async run().
to_anthropic_schema() Claude API-nin gözlədiyi formatı qaytarır.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    async def run(self, **kwargs: Any) -> Any:
        """Tool-un məntiqi. kwargs — Claude-un verdiyi arqumentlər."""
        ...

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
