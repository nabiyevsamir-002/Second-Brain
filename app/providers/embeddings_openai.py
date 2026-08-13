"""OpenAI embedding provider — text-embedding-3-small (1536 ölçü, LOCKED).

RAG semantik axtarış üçün. Yalnız OpenAI SDK.
"""

from __future__ import annotations

from openai import AsyncOpenAI

from app.providers.base import EmbeddingProvider

MODEL = "text-embedding-3-small"


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.last_total_tokens: int = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self.client.embeddings.create(model=MODEL, input=texts)
        self.last_total_tokens = resp.usage.total_tokens
        return [item.embedding for item in resp.data]

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]
