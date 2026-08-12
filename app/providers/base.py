"""Provider interfeysləri (abstract base classes).

Konkret implementasiyalar sonrakı fazalarda əlavə olunacaq:
  - ClaudeLLMProvider        (anthropic)      -> Phase 1
  - WhisperSTTProvider       (openai)         -> Phase 1
  - AzureSTTProvider         (azure speech)   -> Phase 1 (fallback)
  - OpenAIEmbeddingProvider  (text-embedding-3-small) -> Phase 2
  - AzureTTSProvider         (azure speech)   -> Phase 3
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Mətn tamamlama / tool-calling üçün LLM (Claude)."""

    @abstractmethod
    async def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> Any:
        ...


class STTProvider(ABC):
    """Speech-to-Text (səs -> mətn)."""

    @abstractmethod
    async def transcribe(self, audio_path: str, language: str | None = None) -> str:
        ...


class TTSProvider(ABC):
    """Text-to-Speech (mətn -> səs baytları)."""

    @abstractmethod
    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        ...


class EmbeddingProvider(ABC):
    """Mətni vektora çevirir (RAG üçün). 1536 ölçü — LOCKED."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...
