"""Giriş nöqtəsi — botu işə salır (Phase 0)."""

from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import Application

from app.bot.scheduler import setup_jobs
from app.bot.telegram_app import BOT_COMMANDS, build_application
from app.config import settings
from app.db import SessionLocal, check_database
from app.logging_conf import configure_logging, get_logger
from app.providers.factory import init_providers, warmup_local_models
from app.providers.registry import providers
from app.services.reembed import ensure_embedding_model

configure_logging(settings.log_level, settings.environment)
log = get_logger("main")


async def _post_init(application: Application) -> None:
    """Bot başlayandan sonra DB + pgvector yoxlaması."""
    try:
        has_vector = await check_database()
        if has_vector:
            log.info("database_ready", pgvector=True)
        else:
            log.warning(
                "database_ready_no_pgvector",
                pgvector=False,
                hint="pgvector aktiv deyil — init-pgvector.sql işləyibmi?",
            )
    except Exception as exc:  # noqa: BLE001
        log.error("database_check_failed", error=str(exc))

    # Embedding modeli dəyişibsə (məs. VPS-dən köçürülmüş OpenAI vektorları → lokal model)
    # köhnə vektorlar sıfırlanır; reembed_tick onları arxa planda yenidən hesablayır.
    if providers.has("embed"):
        try:
            async with SessionLocal() as session:
                n = await ensure_embedding_model(session, providers.get("embed").model_id)
                await session.commit()
            if n:
                log.warning("embedding_model_changed", invalidated=n,
                            hint="qeydlər arxa planda yenidən embed olunur")
        except Exception as exc:  # noqa: BLE001
            log.error("embedding_model_check_failed", error=str(exc))

    # Lokal modelləri (embedding + Whisper) arxa planda yüklə — ilk dəfə endirilir.
    application.bot_data["warmup"] = asyncio.create_task(asyncio.to_thread(warmup_local_models))

    # "/" menyusu qeydiyyatdakı əmrlərlə sinxron qalsın.
    try:
        await application.bot.set_my_commands(BOT_COMMANDS)
    except Exception as exc:  # noqa: BLE001 — menyu kritik deyil
        log.warning("set_commands_failed", error=str(exc))

    # Proaktiv scheduler (reminders çatdırılması + səhər brifinqi + e-poçt).
    setup_jobs(application)


def main() -> None:
    if not settings.telegram_bot_token:
        log.error("missing_telegram_bot_token")
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN yoxdur — .env faylını yarat və doldur "
            "(.env.example-dan kopyala)."
        )

    log.info(
        "starting_bot",
        environment=settings.environment,
        allowlist=settings.allowed_ids or "OPEN(boş)",
        llm_backend=settings.resolved_llm_backend,
    )

    init_providers()
    application = build_application(post_init=_post_init)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
