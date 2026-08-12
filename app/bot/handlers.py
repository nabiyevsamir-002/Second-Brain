"""Telegram handler-ları (Phase 0 — echo bot).

Növbəti fazalarda buraya səs/mətn qeyd, RAG, tasks və s. əlavə olunacaq.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.logging_conf import get_logger

log = get_logger("bot")

WELCOME = (
    "👋 Salam! Mən sənin şəxsi *Second Brain* assistentinəm.\n\n"
    "Hazırda quruluş mərhələsindəyəm (Phase 0 — echo rejimi): "
    "göndərdiyin mesajı geri qaytarıram.\n\n"
    "Növbəti fazalarda: 🎙 səsli qeydlər, 🔎 RAG axtarış, "
    "⏰ xatırlatmalar və daha çox.\n\n"
    "Əmrlər üçün /help yaz."
)

HELP = (
    "📖 *Əmrlər*\n"
    "/start — başlanğıc\n"
    "/help — bu kömək\n"
    "/id — Telegram ID-ni göstər\n\n"
    "Hazırda echo rejimindəyəm — yazdığını geri qaytarıram."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_markdown(WELCOME)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_markdown(HELP)


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"🆔 Sənin Telegram ID: {user.id}\n"
        f"👤 Ad: {user.full_name}\n\n"
        "Bunu .env-də ALLOWED_USER_IDS dəyərinə yaz."
    )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    log.info("echo", user_id=update.effective_user.id, chars=len(text or ""))
    await update.message.reply_text(f"📝 (echo) {text}")


async def unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    log.warning("unauthorized_access", user_id=user.id, username=user.username)
    await update.message.reply_text(
        "⛔️ Bu şəxsi botdur — sənin girişin yoxdur.\n"
        f"Sənin ID: {user.id}"
    )
