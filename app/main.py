"""Giriş nöqtəsi — botu işə salır (Phase 0)."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application

from app.bot.telegram_app import build_application
from app.config import settings
from app.db import check_database
from app.logging_conf import configure_logging, get_logger

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
    )

    application = build_application(post_init=_post_init)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
