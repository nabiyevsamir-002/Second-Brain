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
from app.services.ingest_service import ingest_document, ingest_url
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
    "*Nə göndərə bilərsən:*\n"
    "• 📝 mətn / 🎙 səs → qeyd və ya sual\n"
    "• 🔗 link → səhifə xülasələnib saxlanılır\n"
    "• 📄 PDF / DOCX → mətn indeksləib axtarışa əlavə olunur"
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


def _first_url(msg) -> str | None:
    for entity in msg.entities or []:
        if entity.type == "url":
            return msg.text[entity.offset : entity.offset + entity.length]
        if entity.type == "text_link":
            return entity.url
    return None


def _is_forward(msg) -> bool:
    return bool(getattr(msg, "forward_origin", None) or getattr(msg, "forward_date", None))


async def _ingest_url_and_reply(update: Update, url: str) -> None:
    user = update.effective_user
    if not (providers.has("llm") and providers.has("embed")):
        await update.message.reply_text("🔗 Link emalı üçün AI açarları lazımdır.")
        return
    await update.message.chat.send_action("typing")
    try:
        async with SessionLocal() as session:
            db_user = await get_or_create_user(session, user.id, name=user.full_name)
            note = await ingest_url(
                session, providers.get("llm"), providers.get("embed"), db_user.telegram_id, url
            )
            await session.commit()
            reply = f"🔗 Linkdən qeyd #{note.id} yaradıldı."
            if note.category:
                reply += f"\n🏷 {note.category}"
            if note.summary:
                reply += f"\n📝 {note.summary}"
    except Exception as exc:  # noqa: BLE001
        log.error("url_ingest_failed", url=url, error=str(exc))
        await update.message.reply_text(f"🔗 Link açıla bilmədi: {exc}")
        return
    await update.message.reply_text(reply)


async def note_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    url = _first_url(msg)
    if url:
        await _ingest_url_and_reply(update, url)
        return
    await update.message.chat.send_action("typing")
    source = NoteSource.forward if _is_forward(msg) else NoteSource.text
    await _run_agent(update, msg.text, source)


async def document_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    filename = doc.file_name or "sənəd"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ("pdf", "docx"):
        await update.message.reply_text("📎 Yalnız PDF və DOCX dəstəklənir.")
        return
    if not (providers.has("llm") and providers.has("embed")):
        await update.message.reply_text("📎 Sənəd emalı üçün AI açarları lazımdır.")
        return

    await update.message.chat.send_action("typing")
    tg_file = await context.bot.get_file(doc.file_id)
    data = bytes(await tg_file.download_as_bytearray())

    try:
        async with SessionLocal() as session:
            db_user = await get_or_create_user(
                session, update.effective_user.id, name=update.effective_user.full_name
            )
            notes, summary = await ingest_document(
                session,
                providers.get("llm"),
                providers.get("embed"),
                db_user.telegram_id,
                filename,
                data,
            )
            await session.commit()
    except ValueError as exc:
        await update.message.reply_text(f"📄 Sənəd emal olunmadı: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        log.error("document_ingest_failed", filename=filename, error=str(exc))
        await update.message.reply_text(f"📄 Sənəd emalında xəta: {exc}")
        return

    reply = f"📄 *{filename}* — {len(notes)} hissə indeksləndi."
    if summary:
        reply += f"\n📝 {summary}"
    await update.message.reply_markdown(reply)


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
