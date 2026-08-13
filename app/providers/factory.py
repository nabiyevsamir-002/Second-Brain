"""Provider factory — settings-dəki açarlara görə provayderləri qeydiyyatdan keçirir.

Açar yoxdursa, həmin provayder qeydiyyatdan keçmir (bot yenə işləyir, sadəcə
həmin funksiya deaktiv olur). Bu, sistemi açar olmadan da qaldırıla bilən edir.
"""

from __future__ import annotations

from app.config import settings
from app.logging_conf import get_logger
from app.providers.embeddings_openai import OpenAIEmbeddingProvider
from app.providers.llm_claude import ClaudeLLMProvider
from app.providers.registry import providers
from app.providers.stt_whisper import WhisperSTTProvider

log = get_logger("providers")


def init_providers() -> None:
    if settings.anthropic_api_key:
        providers.register(
            "llm",
            ClaudeLLMProvider(
                settings.anthropic_api_key,
                settings.claude_model_main,
                settings.claude_model_fast,
            ),
        )
    if settings.openai_api_key:
        providers.register("embed", OpenAIEmbeddingProvider(settings.openai_api_key))
        providers.register("stt", WhisperSTTProvider(settings.openai_api_key))

    log.info(
        "providers_initialized",
        llm=providers.has("llm"),
        embed=providers.has("embed"),
        stt=providers.has("stt"),
    )
