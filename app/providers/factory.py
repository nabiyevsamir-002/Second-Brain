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
                settings.claude_model_smart,
            ),
        )
    if settings.openai_api_key:
        providers.register("embed", OpenAIEmbeddingProvider(settings.openai_api_key))
        providers.register("stt", WhisperSTTProvider(settings.openai_api_key))

    # Azure TTS (səsli cavab) — key + region hər ikisi varsa.
    if settings.azure_speech_key and settings.azure_speech_region:
        from app.providers.tts_azure import AzureTTSProvider

        providers.register(
            "tts",
            AzureTTSProvider(
                settings.azure_speech_key,
                settings.azure_speech_region,
                settings.azure_tts_voice,
            ),
        )

    # Tavily web axtarış — açar varsa (agent web_search tool bundan asılıdır).
    if settings.tavily_api_key:
        from app.providers.search_tavily import TavilySearchProvider

        providers.register("search", TavilySearchProvider(settings.tavily_api_key))

    # Tək tool-using agent — llm + embedder hər ikisi varsa qurulur.
    if providers.has("llm") and providers.has("embed"):
        from app.agent.agent import BrainAgent

        providers.register("agent", BrainAgent(providers.get("llm")))

    log.info(
        "providers_initialized",
        llm=providers.has("llm"),
        embed=providers.has("embed"),
        stt=providers.has("stt"),
        tts=providers.has("tts"),
        search=providers.has("search"),
        agent=providers.has("agent"),
    )
