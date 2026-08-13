"""Telegram handler-ları (Phase 1 — qeyd tutma).

Mətn/səs qeyd → təmizlə → embedding → saxla → təsdiq. `/list` son qeydlər.
"""

from __future__ import annotations

import os
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.logging_conf import get_logger
from app.models import NoteSource
from app.providers.registry import providers
from app.repositories.notes import list_notes
from app.repositories.users import get_or_create_user
from app.services.notes_service import capture_note

log = get_logger("bot")

WELCOME = (
    "👋 Salam! Mən sənin şəxsi *Second Brain* assistentinəm.\n\n"
    "📝 Mətn yaz və ya 🎙 səsli mesaj göndər — mən onu təmizləyir, "
    "kateqoriyalayır və yadda saxlayıram.\n\n"
    "Əmrlər üçün /help yaz."
)

HELP = (
    "📖 *Əmrlər*\n"
    "/start — başlanğıc\n"
    "/help — bu kömək\n"
    "/list — son qeydlər\n"
    "/id — Telegram ID\n\n"
    "Mətn və ya səsli mesaj göndər → qeyd kimi saxlanılır."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_markdown(WELCOME)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_markdown(HELP)


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"🆔 Sənin Telegram ID: {user.id}\n👤 Ad: {user.full_name}"
    )


def _confirmation(note, prefix: str = "✅ Qeyd saxlanıldı.") -> str:
    lines = [prefix]
    if note.category:
        lines.append(f"🏷 *Kateqoriya:* {note.category}")
    if note.tags:
        lines.append("🔖 *Taglar:* " + ", ".join(note.tags))
    if note.summary:
        lines.append(f"📝 {note.summary}")
    return "\n".join(lines)


async def _capture_and_reply(update: Update, raw_text: str, source: NoteSource, prefix: str) -> None:
    user = update.effective_user
    llm = providers.get("llm") if providers.has("llm") else None
    embedder = providers.get("embed") if providers.has("embed") else None

    async with SessionLocal() as session:
        db_user = await get_or_create_user(session, user.id, name=user.full_name)
        note = await capture_note(
            session,
            db_user.telegram_id,
            raw_text,
            source,
            llm=llm,
            embedder=embedder,
        )
        await session.commit()
        text = _confirmation(note, prefix)

    if llm is None:
        text += "\n\n⚠️ AI təmizləmə deaktivdir (ANTHROPIC_API_KEY yoxdur) — xam saxlanıldı."
    await update.message.reply_markdown(text)


async def note_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.chat.send_action("typing")
    await _capture_and_reply(update, update.message.text, NoteSource.text, "✅ Qeyd saxlanıldı.")


async def note_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not providers.has("stt"):
        await update.message.reply_text(
            "🎙 Səs tanıma deaktivdir (OPENAI_API_KEY yoxdur)."
        )
        return

    await update.message.chat.send_action("typing")
    voice = update.message.voice or update.message.audio
    tg_file = await context.bot.get_file(voice.file_id)

    fd, path = tempfile.mkstemp(suffix=".oga")
    os.close(fd)
    try:
        await tg_file.download_to_drive(path)
        stt = providers.get("stt")
        transcript = await stt.transcribe(path, language="az")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    if not transcript:
        await update.message.reply_text("🎙 Səsdən mətn çıxarıla bilmədi, təkrar yoxla.")
        return

    log.info("voice_transcribed", user_id=update.effective_user.id, chars=len(transcript))
    await _capture_and_reply(
        update, transcript, NoteSource.voice, f"🎙 *Transkript:* {transcript}\n\n✅ Qeyd saxlanıldı."
    )


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        notes = await list_notes(session, update.effective_user.id, limit=10)

    if not notes:
        await update.message.reply_text("📭 Hələ qeyd yoxdur. Mətn və ya səs göndər.")
        return

    lines = ["🗒 *Son qeydlər:*\n"]
    for i, note in enumerate(notes, 1):
        icon = "🎙" if note.source == NoteSource.voice else "📝"
        body = note.summary or note.cleaned_text or note.raw_text
        body = body[:80] + ("…" if len(body) > 80 else "")
        cat = f" · _{note.category}_" if note.category else ""
        lines.append(f"{i}. {icon} {body}{cat}")
    await update.message.reply_markdown("\n".join(lines))


async def unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    log.warning("unauthorized_access", user_id=user.id, username=user.username)
    await update.message.reply_text(
        f"⛔️ Bu şəxsi botdur — sənin girişin yoxdur.\nSənin ID: {user.id}"
    )
