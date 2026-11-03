"""Telegram Application-un qurulması + allowlist + handler qeydiyyatı."""

from __future__ import annotations

from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.bot import handlers
from app.config import settings
from app.logging_conf import get_logger

log = get_logger("bot")

# Telegram "/" menyusu — bot hər başlayanda set_my_commands ilə sinxronlaşır
# (yeni əmr əlavə olunanda BotFather-də əl ilə yeniləmək lazım deyil).
BOT_COMMANDS = [
    BotCommand("list", "Son qeydlər (filtr: /list iş, /list #tag)"),
    BotCommand("search", "Qeydlərdə axtarış"),
    BotCommand("related", "Qeydlə əlaqəli qeydlər"),
    BotCommand("pinned", "Sabitlənmiş qeydlər"),
    BotCommand("tasks", "Açıq tapşırıqlar"),
    BotCommand("done", "Tapşırığı bağla"),
    BotCommand("remind", "Gələn xatırlatmalar"),
    BotCommand("stats", "İstifadə, xərc və aylıq büdcə"),
    BotCommand("export", "Qeydləri fayl kimi yüklə"),
    BotCommand("edit", "Qeydi yenilə"),
    BotCommand("delete", "Qeydi sil"),
    BotCommand("settings", "Brifinq və axşam yekunu ayarları"),
    BotCommand("voice", "Səsli cavab"),
    BotCommand("mail", "Son məktublar / bildiriş / təmizlə"),
    BotCommand("health", "Sistem sağlamlığı"),
    BotCommand("help", "Kömək"),
    BotCommand("id", "Telegram ID"),
]


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
    cmd("pinned", handlers.pinned_cmd)
    cmd("search", handlers.search_cmd)
    cmd("related", handlers.related_cmd)
    cmd("tasks", handlers.tasks_cmd)
    cmd("done", handlers.done_cmd)
    cmd("remind", handlers.remind_cmd)
    cmd("stats", handlers.stats_cmd)
    cmd("health", handlers.health_cmd)
    cmd("export", handlers.export_cmd)
    cmd("delete", handlers.delete_cmd)
    cmd("edit", handlers.edit_cmd)
    cmd("settings", handlers.settings_cmd)
    cmd("voice", handlers.voice_cmd)
    cmd("mail", handlers.mail_cmd)

    # Inline düymə callback-ları (/delete təsdiqi, /settings). Düymələr yalnız
    # allowlist istifadəçisinin şəxsi çatında göndərilir.
    app.add_handler(CallbackQueryHandler(handlers.on_callback))

    text_filter = filters.TEXT & ~filters.COMMAND
    voice_filter = filters.VOICE | filters.AUDIO
    doc_filter = filters.Document.ALL
    photo_filter = filters.PHOTO
    if user_filter is not None:
        text_filter = text_filter & user_filter
        voice_filter = voice_filter & user_filter
        doc_filter = doc_filter & user_filter
        photo_filter = photo_filter & user_filter

    app.add_handler(MessageHandler(text_filter, handlers.note_text))
    app.add_handler(MessageHandler(voice_filter, handlers.note_voice))
    app.add_handler(MessageHandler(doc_filter, handlers.document_note))
    app.add_handler(MessageHandler(photo_filter, handlers.photo_note))


def build_application(post_init=None) -> Application:
    builder = Application.builder().token(settings.telegram_bot_token)
    if post_init is not None:
        builder = builder.post_init(post_init)
    app = builder.build()
    app.add_error_handler(handlers.on_error)

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
