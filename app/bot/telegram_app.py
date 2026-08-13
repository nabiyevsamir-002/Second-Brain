"""Telegram Application-un qurulması + allowlist + handler qeydiyyatı."""

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


def _register_common(app: Application, user_filter=None) -> None:
    """/start /help /id /list + mətn və səs qeyd handler-ləri."""

    def cmd(name, cb):
        if user_filter is not None:
            app.add_handler(CommandHandler(name, cb, filters=user_filter))
        else:
            app.add_handler(CommandHandler(name, cb))

    cmd("start", handlers.start)
    cmd("help", handlers.help_cmd)
    cmd("id", handlers.whoami)
    cmd("list", handlers.list_cmd)

    text_filter = filters.TEXT & ~filters.COMMAND
    voice_filter = filters.VOICE | filters.AUDIO
    if user_filter is not None:
        text_filter = text_filter & user_filter
        voice_filter = voice_filter & user_filter

    app.add_handler(MessageHandler(text_filter, handlers.note_text))
    app.add_handler(MessageHandler(voice_filter, handlers.note_voice))


def build_application(post_init=None) -> Application:
    builder = Application.builder().token(settings.telegram_bot_token)
    if post_init is not None:
        builder = builder.post_init(post_init)
    app = builder.build()

    allowed = settings.allowed_ids
    if allowed:
        user_filter = filters.User(user_id=allowed)
        _register_common(app, user_filter)
        # Allowlist-də olmayan hər kəs -> unauthorized.
        app.add_handler(MessageHandler(~user_filter, handlers.unauthorized))
        log.info("allowlist_enabled", allowed_ids=allowed)
    else:
        _register_common(app, None)
        log.warning(
            "allowlist_empty_open_mode",
            hint="ALLOWED_USER_IDS boşdur — /id ilə öz ID-ni öyrən və .env-ə yaz.",
        )

    return app
