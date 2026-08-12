"""Telegram Application-un qurulması + allowlist.

allowlist (ALLOWED_USER_IDS) doludursa: yalnız o ID-lər bota giriş edir,
qalanları "unauthorized" cavabı alır.
allowlist boşdursa: "open mode" — hamı giriş edir (yalnız ilk quraşdırma /
ID öyrənmək üçün). İstifadədən əvvəl mütləq öz ID-ni əlavə et.
"""

from __future__ import annotations

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.bot import handlers
from app.config import settings
from app.logging_conf import get_logger

log = get_logger("bot")


def build_application(post_init=None) -> Application:
    builder = Application.builder().token(settings.telegram_bot_token)
    if post_init is not None:
        builder = builder.post_init(post_init)
    app = builder.build()

    allowed = settings.allowed_ids

    if allowed:
        user_filter = filters.User(user_id=allowed)

        app.add_handler(CommandHandler("start", handlers.start, filters=user_filter))
        app.add_handler(CommandHandler("help", handlers.help_cmd, filters=user_filter))
        app.add_handler(CommandHandler("id", handlers.whoami, filters=user_filter))
        app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & user_filter, handlers.echo
            )
        )
        # Allowlist-də olmayan hər kəs -> unauthorized.
        app.add_handler(MessageHandler(~user_filter, handlers.unauthorized))
        log.info("allowlist_enabled", allowed_ids=allowed)
    else:
        # allowlist boş — bootstrap/open mode.
        app.add_handler(CommandHandler("start", handlers.start))
        app.add_handler(CommandHandler("help", handlers.help_cmd))
        app.add_handler(CommandHandler("id", handlers.whoami))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.echo)
        )
        log.warning(
            "allowlist_empty_open_mode",
            hint="ALLOWED_USER_IDS boşdur — /id ilə öz ID-ni öyrən və .env-ə yaz.",
        )

    return app
