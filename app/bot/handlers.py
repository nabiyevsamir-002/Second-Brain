"""Telegram handler-ları (Phase 2 — tool-using agent + RAG).

Mətn/səs → agent niyyəti routing edir (save_note / search_notes) → cavab.
/search RAG axtarış. /list son qeydlər. Agent yoxdursa xam saxlamaya fallback.
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
from app.repositories.messages import add_message, get_recent_messages
from app.repositories.notes import list_notes, search_notes_by_vector
from app.repositories.users import get_or_create_user
from app.services.notes_service import capture_note

log = get_logger("bot")

WELCOME = (
    "👋 Salam! Mən sənin şəxsi *Second Brain* assistentinəm.\n\n"
    "📝 Mətn və ya 🎙 səs göndər — mən niyyətini anlayıram:\n"
    "• qeyddirsə → təmizləyib saxlayıram\n"
    "• sualdırsa → qeydlərində axtarıb sitatla cavab verirəm\n\n"
    "Əmrlər üçün /help yaz."
)

HELP = (
    "📖 *Əmrlər*\n"
    "/start — başlanğıc\n"
    "/help — bu kömək\n"
    "/list — son qeydlər\n"
    "/search <söz> — qeydlərdə axtarış\n"
    "/id — Telegram ID\n\n"
    "Mətn/səs göndər → agent qeyd saxlayır və ya sualına cavab verir."
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


async def _run_agent(update: Update, raw_text: str, source: NoteSource, prefix: str = "") -> None:
    user = update.effective_user
    agent = providers.get("agent") if providers.has("agent") else None

    # Fallback: agent yoxdursa (açar yoxdur) — xam saxla.
    if agent is None:
        async with SessionLocal() as session:
            db_user = await get_or_create_user(session, user.id, name=user.full_name)
            note = await capture_note(session, db_user.telegram_id, raw_text, source)
            await session.commit()
        await update.message.reply_text(
            f"{prefix}✅ Qeyd #{note.id} saxlanıldı (xam — AI deaktiv)."
        )
        return

    async with SessionLocal() as session:
        db_user = await get_or_create_user(session, user.id, name=user.full_name)
        history = await get_recent_messages(session, db_user.telegram_id, limit=6)
        reply = await agent.handle(
            session,
            db_user.telegram_id,
            raw_text,
            source,
            providers.get("embed"),
            history,
        )
        await add_message(session, db_user.telegram_id, "user", raw_text)
        await add_message(session, db_user.telegram_id, "assistant", reply)
        await session.commit()

    # Plain text — agent cavabındakı [#id] və s. Markdown-ı pozmasın deyə.
    await update.message.reply_text(prefix + reply)


async def note_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.chat.send_action("typing")
    await _run_agent(update, update.message.text, NoteSource.text)


async def note_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not providers.has("stt"):
        await update.message.reply_text("🎙 Səs tanıma deaktivdir (OPENAI_API_KEY yoxdur).")
        return

    await update.message.chat.send_action("typing")
    voice = update.message.voice or update.message.audio
    tg_file = await context.bot.get_file(voice.file_id)

    fd, path = tempfile.mkstemp(suffix=".oga")
    os.close(fd)
    try:
        await tg_file.download_to_drive(path)
        transcript = await providers.get("stt").transcribe(path, language="az")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    if not transcript:
        await update.message.reply_text("🎙 Səsdən mətn çıxarıla bilmədi, təkrar yoxla.")
        return

    log.info("voice_transcribed", user_id=update.effective_user.id, chars=len(transcript))
    await _run_agent(update, transcript, NoteSource.voice, prefix=f"🎙 _{transcript}_\n\n")


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


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await update.message.reply_text("İstifadə: /search <axtarış sözü>")
        return
    if not providers.has("embed"):
        await update.message.reply_text("🔎 Axtarış deaktivdir (OPENAI_API_KEY yoxdur).")
        return

    async with SessionLocal() as session:
        embedding = await providers.get("embed").embed_one(query)
        hits = await search_notes_by_vector(session, update.effective_user.id, embedding, k=5)

    if not hits:
        await update.message.reply_text(f"🔎 '{query}' üzrə nəticə tapılmadı.")
        return

    lines = [f"🔎 *'{query}'* üzrə nəticələr:\n"]
    for note, dist in hits:
        icon = "🎙" if note.source == NoteSource.voice else "📝"
        body = note.summary or note.cleaned_text or note.raw_text
        body = body[:70] + ("…" if len(body) > 70 else "")
        pct = round(max(0.0, 1.0 - dist) * 100)
        lines.append(f"#{note.id} {icon} {body} · {pct}%")
    await update.message.reply_markdown("\n".join(lines))


async def unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    log.warning("unauthorized_access", user_id=user.id, username=user.username)
    await update.message.reply_text(
        f"⛔️ Bu şəxsi botdur — sənin girişin yoxdur.\nSənin ID: {user.id}"
    )
