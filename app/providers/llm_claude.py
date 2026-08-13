"""Claude LLM provider (Anthropic SDK) — layihənin "beyni".

Yalnız Anthropic SDK istifadə olunur (OpenAI provayderləri ayrı fayllardadır).
Modellər settings-dən: claude-sonnet-5 (main), claude-haiku-4-5 (fast).
"""

from __future__ import annotations

from typing import Any

from anthropic import AsyncAnthropic

from app.providers.base import LLMProvider


class ClaudeLLMProvider(LLMProvider):
    def __init__(self, api_key: str, model_main: str, model_fast: str) -> None:
        self.client = AsyncAnthropic(api_key=api_key)
        self.model_main = model_main
        self.model_fast = model_fast

    async def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> Any:
        params: dict[str, Any] = {
            "model": model or self.model_main,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if tools:
            params["tools"] = tools
        params.update(kwargs)
        return await self.client.messages.create(**params)

    @staticmethod
    def text_of(response: Any) -> str:
        """Cavabdakı text bloklarını birləşdir."""
        return "".join(b.text for b in response.content if b.type == "text")
