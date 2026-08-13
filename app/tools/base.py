"""Tool interfeysi + icra konteksti — Claude function-calling üçün.

Agent gələn mesajın niyyətini anlayıb uyğun tool-u çağırır. Hər tool:
name, description, input_schema (Claude-a ötürülür) və async run(ctx, **input).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ToolContext:
    """Tool icrası üçün per-request kontekst."""

    session: AsyncSession
    user_id: int
    llm: Any
    embedder: Any
    source: Any  # NoteSource (save üçün)
    saved_note: Any = None
    related: list[Any] = field(default_factory=list)


class Tool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    async def run(self, ctx: ToolContext, **kwargs: Any) -> str:
        """Tool məntiqi. Claude-a qaytarılacaq mətn (tool_result) qaytarır."""
        ...

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
