"""Provider factory — settings-ə görə provayderləri qeydiyyatdan keçirir.

Backend seçimi (Phase 8):
  • LLM: subscription (Claude abunəsi, CLAUDE_CODE_OAUTH_TOKEN) | api (ANTHROPIC_API_KEY)
  • embedding / STT: local (API açarsız, CPU) | openai (OPENAI_API_KEY)
`auto` rejimində açarlara baxılır — beləliklə köhnə API konfiqurasiyası (VPS) dəyişmədən
işləyir, açarsız PC isə avtomatik abunə + lokal modellərə keçir.
Konfiqurasiyası olmayan provayder qeydiyyatdan keçmir (həmin funksiya deaktiv olur).
"""

from __future__ import annotations

import os

from app.config import settings
from app.logging_conf import get_logger
from app.providers.registry import providers

log = get_logger("providers")


def _cache(sub: str) -> str | None:
    return os.path.join(settings.model_cache_dir, sub) if settings.model_cache_dir else None


def _openai_or_local(kind: str, value: str) -> str:
    backend = settings.resolved_backend(value)
    if backend == "openai" and not settings.openai_api_key:
        log.warning("openai_key_missing_using_local", kind=kind)
        return "local"
    return backend


def init_providers() -> None:
    llm_backend = settings.resolved_llm_backend
    if llm_backend == "subscription":
        from app.providers.llm_subscription import SubscriptionLLMProvider

        providers.register(
            "llm",
            SubscriptionLLMProvider(
                settings.claude_model_main,
                settings.claude_model_fast,
                settings.claude_model_smart,
                oauth_token=settings.claude_code_oauth_token,
                timeout_sec=settings.llm_timeout_sec,
            ),
        )
    elif llm_backend == "api":
        from app.providers.llm_claude import ClaudeLLMProvider

        providers.register(
            "llm",
            ClaudeLLMProvider(
                settings.anthropic_api_key,
                settings.claude_model_main,
                settings.claude_model_fast,
                settings.claude_model_smart,
            ),
        )

    embed_backend = _openai_or_local("embed", settings.embed_backend)
    if embed_backend == "openai":
        from app.providers.embeddings_openai import OpenAIEmbeddingProvider

        providers.register("embed", OpenAIEmbeddingProvider(settings.openai_api_key))
    else:
        from app.providers.embeddings_local import LocalEmbeddingProvider

        providers.register(
            "embed", LocalEmbeddingProvider(settings.local_embed_model, cache_dir=_cache("fastembed"))
        )

    stt_backend = _openai_or_local("stt", settings.stt_backend)
    if stt_backend == "openai":
        from app.providers.stt_whisper import WhisperSTTProvider

        providers.register("stt", WhisperSTTProvider(settings.openai_api_key))
    else:
        from app.providers.stt_local import LocalWhisperSTTProvider

        providers.register(
            "stt",
            LocalWhisperSTTProvider(
                settings.whisper_model,
                cache_dir=_cache("whisper"),
                compute_type=settings.whisper_compute_type,
            ),
        )

    # Azure TTS (səsli cavab) — key + region hər ikisi varsa (istəyə bağlı).
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

    # Tavily — yalnız API agenti üçün (abunə agenti daxili WebSearch işlədir).
    if settings.tavily_api_key and llm_backend == "api":
        from app.providers.search_tavily import TavilySearchProvider

        providers.register("search", TavilySearchProvider(settings.tavily_api_key))

    # E-poçt (IMAP, yalnız oxuma) — host + ünvan + parol varsa.
    if settings.email_enabled:
        from app.providers.email_imap import ImapMailProvider

        providers.register(
            "email",
            ImapMailProvider(
                settings.email_imap_host,
                settings.email_imap_port,
                settings.email_address,
                settings.email_password,
                folder=settings.email_folder,
                ssl=settings.email_imap_ssl,
            ),
        )

    # Tək tool-using agent — llm + embedder hər ikisi varsa qurulur.
    if providers.has("llm") and providers.has("embed"):
        if llm_backend == "subscription":
            from app.agent.sdk_agent import SDKBrainAgent, default_tools

            agent = SDKBrainAgent(
                providers.get("llm"), default_tools(), max_turns=settings.agent_max_turns
            )
        else:
            from app.agent.agent import BrainAgent

            agent = BrainAgent(providers.get("llm"))
        providers.register("agent", agent)

    log.info(
        "providers_initialized",
        llm=llm_backend,
        embed=embed_backend,
        stt=stt_backend,
        tts=providers.has("tts"),
        search=providers.has("search"),
        email=providers.has("email"),
        agent=providers.has("agent"),
    )


def warmup_local_models() -> None:
    """Lokal modelləri (embedding + Whisper) yüklə — ilk işə salmada endirilir.

    Thread-də çağırılır ki, bot bu müddətdə cavab verə bilsin.
    """
    for key in ("embed", "stt"):
        provider = providers.get(key) if providers.has(key) else None
        if provider is not None and hasattr(provider, "warmup"):
            try:
                provider.warmup()
                log.info("model_ready", provider=key)
            except Exception as exc:  # noqa: BLE001
                log.error("model_warmup_failed", provider=key, error=str(exc))
