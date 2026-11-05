"""Telegram handler-ları (Phase 2 — tool-using agent + RAG).

Mətn/səs → agent niyyəti routing edir (save_note / search_notes) → cavab.
/search RAG axtarış. /list son qeydlər. Agent yoxdursa xam saxlamaya fallback.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import re
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from anthropic import APIError
from sqlalchemy import text
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, Conflict, NetworkError, TelegramError
from telegram.ext import ContextTypes

# Proses başlama anı (uptime üçün) — modul importunda = app start.
_STARTED = time.monotonic()

from app.bot.md import md, md_in, plain_text, split_message
from app.bot.ratelimit import limiter
from app.config import settings
from app.db import SessionLocal
from app.logging_conf import get_logger
from app.models import NoteSource, Reminder
from app.pricing import stt_cost, tts_cost
from app.providers.errors import LLMUnavailableError, SubscriptionLimitError
from app.providers.registry import providers
from app.repositories.links import find_related, related_threshold
from app.repositories.messages import add_message, count_messages, get_recent_messages
from app.repositories.notes import (
    all_notes,
    delete_all_notes,
    delete_note,
    get_note,
    hybrid_search_notes,
    list_notes,
    set_pinned,
)
from app.repositories.reminders import create_reminder, list_pending
from app.repositories.tasks import complete_task, list_open_tasks
from app.repositories.usage import log_usage, usage_totals
from app.repositories.users import get_or_create_user, update_settings
from app.services.budget import (
    get_budget_status,
    month_key,
    notice_text,
    pending_notice,
    status_for,
)
from app.services.ingest_service import ingest_document, ingest_image, ingest_url
from app.services.email_watch import is_mail_owner, short_sender
from app.services.journal import is_journal_reply, save_journal
from app.services.mail_review import MAX_KEPT, build_proposal
from app.services.notes_service import capture_note, recapture_note
from app.timeutils import fmt_local, now_local, now_utc
from app.tools.email_tools import MAX_BODY_CHARS

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
    "/list — son qeydlər (☆ sabitlə · 🗑 sil düymələri; /list iş · /list #tag = filtr)\n"
    "/pinned — sabitlənmiş (pin) qeydlər\n"
    "/search <söz> — qeydlərdə axtarış (cat:iş və ya #tag filtr)\n"
    "/related <id> — qeydlə əlaqəli qeydlər\n"
    "/tasks — açıq tapşırıqlar\n"
    "/done <id> — tapşırığı bağla\n"
    "/remind — gələn xatırlatmalar\n"
    "/stats — istifadə, xərc və aylıq büdcə\n"
    "/health — sistem sağlamlığı (DB, providerlər, uptime)\n"
    "/export — qeydləri fayl kimi yüklə\n"
    "/delete <id> — qeydi sil (/delete all = hamısı)\n"
    "/edit <id> <mətn> — qeydi yenilə (yenidən təmizlə+embed)\n"
    "/settings — brifinq və axşam yekunu ayarları\n"
    "/voice — səsli cavab (aç/söndür, səs seç)\n"
    "/mail — son məktublar (/mail <uid> oxu · /mail on|off bildiriş)\n"
    "/mail təmizlə — reklam məktublarını düymə ilə arxivlə (heç nə silinmir)\n"
    "/mail sil — lazımsız məktubları Claude tapır, təsdiqlə Zibil qutusuna köçür\n"
    "/id — Telegram ID\n\n"
    "*Nə göndərə bilərsən:*\n"
    "• 📝 mətn / 🎙 səs → qeyd, sual, tapşırıq və ya xatırlatma\n"
    "• ⏰ «sabah 9-da həkimə zəng etməyi xatırlat» → xatırlatma qururam\n"
    "• 📋 «hesabatı bitirmək tapşırığı əlavə et» → tapşırıq (təkrarlanan da: «hər həftə...»)\n"
    "• 🧾 «iş qeydlərimi xülasə et» → kateqoriyanın icması\n"
    "• 📊 «bu həftə nə etdim?» → fəaliyyət icmalı\n"
    "• 🌙 22:00-dakı axşam yekununa cavab ver (Reply) → gündəlik qeydi\n"
    "• 🧩 «#12 ilə əlaqəli nə var?» → əlaqəli qeydlər\n"
    "• 📧 «yeni məktublarım var?», «Əlidən gələn məktubu xülasə et» → e-poçt\n"
    "• 🗑 «lazımsız məktubları sil» → siyahı səbəbi ilə, silmə yalnız düymə ilə\n"
    "• 🔗 link → səhifə xülasələnib saxlanılır\n"
    "• 📄 PDF / DOCX → mətn indeksləib axtarışa əlavə olunur\n"
    "• 🖼 şəkil / skrinşot → Claude vision oxuyur (OCR) və qeyd yaradır\n"
    "• 🌐 «internetdə axtar...», cari xəbər/hava/qiymət → web axtarış (mənbə URL-li)"
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


def _fmt_uptime(secs: float) -> str:
    secs = int(secs)
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d}g")
    if h:
        parts.append(f"{h}s")
    parts.append(f"{m}dəq")
    return " ".join(parts)


def backend_label() -> str:
    """Aktiv AI backend-lərin qısa təsviri (/health)."""
    llm = {"subscription": "Claude abunəsi (Claude Code)", "api": "Anthropic API"}.get(
        settings.resolved_llm_backend, "yoxdur"
    )
    embed = getattr(providers.get("embed"), "model_id", "?") if providers.has("embed") else "yox"
    if not providers.has("stt"):
        stt = "yox"
    elif getattr(providers.get("stt"), "local", False):
        stt = f"lokal Whisper ({settings.whisper_model})"
    else:
        stt = "OpenAI Whisper"
    mail = "qoşulub" if providers.has("email") else "yox"
    return f"{llm} · embed: {embed} · STT: {stt} · e-poçt: {mail}"


async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/health — DB, providerlər, sayğaclar, uptime, monitoring statusu (əl ilə yoxlama)."""
    db_ok = True
    n_notes = n_users = 0
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            n_notes = int((await session.execute(text("SELECT count(*) FROM notes"))).scalar() or 0)
            n_users = int((await session.execute(text("SELECT count(*) FROM users"))).scalar() or 0)
    except Exception as exc:  # noqa: BLE001
        db_ok = False
        log.error("health_db_fail", error=str(exc))

    prov = ", ".join(
        k for k in ("llm", "embed", "stt", "tts", "search", "agent") if providers.has(k)
    ) or "yoxdur"
    mon = "açıq 🟢" if settings.healthcheck_url else "söndürülü ⚪"
    lines = [
        "🩺 *Sağlamlıq*",
        f"DB: {'✅ qoşulu' if db_ok else '❌ XƏTA'}",
        f"Providerlər: {prov}",
        md(f"AI: {backend_label()}"),
        f"Qeyd / İstifadəçi: {n_notes} / {n_users}",
        f"Uptime: {_fmt_uptime(time.monotonic() - _STARTED)}",
        f"Monitoring ping: {mon}",
    ]
    await update.message.reply_markdown("\n".join(lines))


@contextlib.asynccontextmanager
async def _keep_typing(update: Update):
    """Telegram «yazır…» ~5 saniyə yaşayır, abunə agentinin cavabı isə 7-20 saniyə çəkir."""

    async def loop() -> None:
        while True:
            with contextlib.suppress(Exception):  # göstərici kritik deyil
                await update.message.chat.send_action("typing")
            await asyncio.sleep(4)

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _rate_ok(update: Update) -> bool:
    """Bahalı əməliyyatlar üçün rate-limit yoxlaması. Aşılıbsa istifadəçiyə bildir."""
    allowed, retry = limiter.check(update.effective_user.id)
    if not allowed:
        await update.message.reply_text(
            f"⏳ Bir az yavaş — çox sürətli göndərirsən. Təxminən {retry} saniyə sonra "
            "yenidən cəhd et."
        )
    return allowed


def _llm_failure_text(exc: Exception) -> str:
    if isinstance(exc, SubscriptionLimitError):
        when = ""
        if exc.resets_at:
            reset = datetime.fromtimestamp(exc.resets_at, tz=timezone.utc)
            when = f" — {fmt_local(reset, with_weekday=False)}-də bərpa olunur"
        return f"⏳ Claude abunə limiti doldu{when}."
    return f"⚠️ Claude hazırda cavab vermir ({exc})."


async def _save_after_llm_failure(session, uid: int, raw_text: str, source, exc) -> str:
    """AI əlçatmazdır: alətlərin etdiyini saxla; heç bir alət işləməyibsə mesajı xam qeyd et."""
    note = None
    try:
        if not getattr(exc, "tools_ran", None):
            embedder = providers.get("embed") if providers.has("embed") else None
            note = await capture_note(session, uid, raw_text, source, embedder=embedder)
        await session.commit()
    except Exception as err:  # noqa: BLE001
        await session.rollback()
        note = None
        log.error("raw_save_failed", user_id=uid, error=str(err))
    log.warning("llm_unavailable", user_id=uid, error=str(exc),
                limit=isinstance(exc, SubscriptionLimitError))
    reply = _llm_failure_text(exc)
    if note is not None:
        reply += f"\n📝 Mesajın itməsin deyə xam qeyd #{note.id} kimi saxladım."
    return reply


async def _budget_after_reply(uid: int, s: dict, fallback):
    """Cavabdan SONRA büdcəni yenidən yoxla (bu mesajın xərci də daxil).

    Returns (status, bildiriş | None) — hər hədd (warn/over) ayda bir dəfə bildirilir.
    Xəta olsa cavabı bloklamır: fallback status qaytarılır.
    """
    try:
        async with SessionLocal() as session:
            status = await get_budget_status(session, uid)
            month = month_key()
            level = pending_notice(status.state, month, s.get("budget_notified"))
            if level is None:
                return status, None
            await update_settings(session, uid, {"budget_notified": f"{month}:{level}"})
            await session.commit()
        log.info("budget_notice", user_id=uid, level=level, spent=str(status.spent))
        return status, notice_text(status)
    except Exception as exc:  # noqa: BLE001 — büdcə yoxlaması kritik deyil
        log.warning("budget_check_failed", user_id=uid, error=str(exc))
        return fallback, None


# --- Səsli cavab (Azure az-AZ TTS) ---------------------------------------

# Səs adları — istifadəçi /voice babek | banu ilə seçir.
AZ_VOICES = {"babek": "az-AZ-BabekNeural", "banu": "az-AZ-BanuNeural"}
_VOICE_LABELS = {"az-AZ-BabekNeural": "Babek 👨", "az-AZ-BanuNeural": "Banu 👩"}
MAX_TTS_CHARS = 1500  # uzun cavabları kəs (latency + xərc nəzarəti)

_CITE_RE = re.compile(r"\[#\d+\]")  # RAG sitatları ([#12]) — səsdə oxunmasın
_MD_RE = re.compile(r"[*_`#>|]")  # Markdown işarələri
_EMOJI_RE = re.compile(
    "["
    "\U0001f000-\U0001faff"  # emoji, simvol, piktoqram blokları
    "\U00002300-\U000023ff"  # texniki simvollar (⏰ ⌛ ⏳ …)
    "\U00002600-\U000027bf"  # müxtəlif simvollar + dingbats
    "\U0001f1e6-\U0001f1ff"  # regional indicator (bayraqlar)
    "\U00002190-\U000021ff"  # oxlar
    "\U00002b00-\U00002bff"  # müxtəlif simvol/oxlar
    "\U0000fe0f"             # variation selector-16
    "\U0000200d"             # zero-width joiner
    "]"
)


def _clean_for_speech(text: str) -> str:
    """Mətni səsə uyğunlaşdır: sitat, markdown və emojiləri təmizlə, kəs."""
    t = _CITE_RE.sub("", text)
    t = _EMOJI_RE.sub("", t)
    t = _MD_RE.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > MAX_TTS_CHARS:
        t = t[:MAX_TTS_CHARS].rsplit(" ", 1)[0] + "…"
    return t


def _voice_settings(user_settings: dict | None) -> tuple[bool, str]:
    """(voice_reply açıqdır?, səs adı) — default söndürülü + config səsi."""
    s = user_settings or {}
    enabled = bool(s.get("voice_reply", False))
    name = s.get("voice_name") or settings.azure_tts_voice
    return enabled, name


async def _speak_reply(update: Update, text: str, voice_name: str | None = None) -> None:
    """Mətn cavabını Azure TTS ilə səsli qeyd kimi göndər (səssiz uğursuzluq)."""
    if not providers.has("tts"):
        return
    spoken = _clean_for_speech(text)
    if not spoken:
        return
    try:
        await update.message.chat.send_action("record_voice")
        audio = await providers.get("tts").synthesize(spoken, voice=voice_name)
    except Exception as exc:  # noqa: BLE001 — səsli cavab kritik deyil, mətn onsuz da gedib
        log.error("tts_failed", error=str(exc))
        return

    try:
        async with SessionLocal() as session:
            await log_usage(session, update.effective_user.id, "tts", cost=tts_cost(len(spoken)))
            await session.commit()
    except Exception:  # noqa: BLE001 — usage logu kritik deyil
        pass

    bio = io.BytesIO(audio)
    bio.name = "reply.ogg"
    await update.message.reply_voice(voice=bio)
    log.info("voice_reply_sent", user_id=update.effective_user.id, chars=len(spoken))


async def _run_agent(
    update: Update,
    raw_text: str,
    source: NoteSource,
    prefix: str = "",
    input_is_voice: bool = False,
) -> None:
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
        # Soft büdcə: limit keçilibsə mesaj Sonnet-ə qalxmır (Haiku qalır).
        budget = await get_budget_status(session, db_user.telegram_id)
        history = await get_recent_messages(session, db_user.telegram_id, limit=6)
        try:
            async with _keep_typing(update):
                reply = plain_text(await agent.handle(
                    session,
                    db_user.telegram_id,
                    raw_text,
                    source,
                    providers.get("embed"),
                    history,
                    allow_escalation=not budget.degraded,
                ))
        except (LLMUnavailableError, APIError) as exc:
            notice = await _save_after_llm_failure(session, db_user.telegram_id, raw_text, source, exc)
            await update.message.reply_text(prefix + notice)
            return
        await add_message(session, db_user.telegram_id, "user", raw_text)
        await add_message(session, db_user.telegram_id, "assistant", reply)
        await session.commit()
        s = db_user.settings or {}
        voice_on, voice_name = _voice_settings(s)
        voice_mirror = bool(s.get("voice_mirror", True))

    # Plain text — agent cavabındakı [#id] və s. Markdown-ı pozmasın deyə.
    for part in split_message(prefix + reply):
        await update.message.reply_text(part)

    # Agent lazımsız məktublara baxıbsa: siyahı + təsdiq düymələri ayrıca mesajla.
    trash = s.get("mail_trash") or {}
    if trash.get("deliver"):
        await _deliver_trash_proposal(update, trash)

    # Bu mesajın xərci də daxil: hədd indi keçilibsə səs söndürülür + bir dəfə bildiriş.
    budget, notice = await _budget_after_reply(user.id, s, budget)

    # Səsli cavab: açıqdırsa HƏR mesajda; ya da səslə yazıblarsa (mirror) səslə cavab ver.
    # Büdcə limiti keçilibsə (soft rejim) səsli cavab getmir.
    if not budget.degraded and (voice_on or (voice_mirror and input_is_voice)):
        await _speak_reply(update, reply, voice_name)

    if notice:
        await update.message.reply_text(notice)


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


async def _save_journal_reply(
    update: Update, text: str, source: NoteSource, prefix: str = ""
) -> None:
    """Axşam yekununa cavab → «gündəlik» qeydi (agentsiz, Claude-suz)."""
    user = update.effective_user
    embedder = providers.get("embed") if providers.has("embed") else None
    async with SessionLocal() as session:
        db_user = await get_or_create_user(session, user.id, name=user.full_name)
        note = await save_journal(session, db_user.telegram_id, text, source, embedder)
        await session.commit()
    log.info("journal_saved", note_id=note.id, user_id=user.id)
    await update.message.reply_text(f"{prefix}📝 Gündəliyə yazdım — qeyd #{note.id}.")


async def note_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _rate_ok(update):
        return
    msg = update.message
    if is_journal_reply(msg, context.bot.id):
        await _save_journal_reply(update, msg.text, NoteSource.text)
        return
    url = _first_url(msg)
    if url:
        await _ingest_url_and_reply(update, url)
        return
    await update.message.chat.send_action("typing")
    source = NoteSource.forward if _is_forward(msg) else NoteSource.text
    await _run_agent(update, msg.text, source)


async def document_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _rate_ok(update):
        return
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

    reply = f"📄 {md(filename)} — {len(notes)} hissə indeksləndi."
    if summary:
        reply += f"\n📝 {md(summary)}"
    await update.message.reply_markdown(reply)


async def photo_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram şəklini Claude vision ilə oxu (OCR + təsvir) → qeyd."""
    if not await _rate_ok(update):
        return
    if not (providers.has("llm") and providers.has("embed")):
        await update.message.reply_text("🖼 Şəkil emalı üçün AI açarları lazımdır.")
        return
    photos = update.message.photo
    if not photos:
        return
    photo = photos[-1]  # ən böyük ölçü
    tg_file = await context.bot.get_file(photo.file_id)
    data = bytes(await tg_file.download_as_bytearray())
    caption = (update.message.caption or "").strip()

    await update.message.chat.send_action("typing")
    try:
        async with SessionLocal() as session:
            db_user = await get_or_create_user(
                session, update.effective_user.id, name=update.effective_user.full_name
            )
            note = await ingest_image(
                session,
                providers.get("llm"),
                providers.get("embed"),
                db_user.telegram_id,
                data,
                caption=caption,
            )
            await session.commit()
            reply = f"🖼 Şəkildən qeyd #{note.id} yaradıldı."
            if note.category:
                reply += f"\n🏷 {note.category}"
            if note.summary:
                reply += f"\n📝 {note.summary}"
    except ValueError as exc:
        await update.message.reply_text(f"🖼 Şəkil emal olunmadı: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        log.error("photo_ingest_failed", error=str(exc))
        await update.message.reply_text(f"🖼 Şəkil emalında xəta: {exc}")
        return
    await update.message.reply_text(reply)


VOICE_DOWNLOAD_ATTEMPTS = 3
VOICE_RETRY_DELAY_SEC = 1


async def _download_voice(bot, file_id: str, path: str) -> None:
    """Səsi Telegram-dan yüklə; şəbəkə qırılanda təkrar cəhd et (BadRequest təkrarlanmır)."""
    for attempt in range(1, VOICE_DOWNLOAD_ATTEMPTS + 1):
        try:
            tg_file = await bot.get_file(file_id)
            await tg_file.download_to_drive(path)
            return
        except BadRequest:
            raise
        except NetworkError as exc:  # TimedOut da NetworkError-dur
            if attempt == VOICE_DOWNLOAD_ATTEMPTS:
                raise
            log.warning("voice_download_retry", attempt=attempt, error=repr(exc))
            await asyncio.sleep(VOICE_RETRY_DELAY_SEC * attempt)


async def note_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _rate_ok(update):
        return
    if not providers.has("stt"):
        await update.message.reply_text("🎙 Səs tanıma deaktivdir (OPENAI_API_KEY yoxdur).")
        return

    voice = update.message.voice or update.message.audio
    fd, path = tempfile.mkstemp(suffix=".oga")
    os.close(fd)
    try:
        async with _keep_typing(update):  # böyük modeldə çevrilmə onlarla saniyə çəkir
            await _download_voice(context.bot, voice.file_id, path)
            started = time.monotonic()
            transcript = await providers.get("stt").transcribe(path, language="az")
            stt_sec = round(time.monotonic() - started, 1)
    except TelegramError as exc:
        log.warning("voice_download_failed", error=repr(exc))
        await update.message.reply_text("🎙 Səsi Telegram-dan yükləmək alınmadı, yenidən göndər.")
        return
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    if not transcript:
        await update.message.reply_text("🎙 Səsdən mətn çıxarıla bilmədi, təkrar yoxla.")
        return

    # STT xərcini logla (audio uzunluğuna görə).
    try:
        duration = getattr(voice, "duration", 0) or 0
        async with SessionLocal() as session:
            await get_or_create_user(
                session, update.effective_user.id, name=update.effective_user.full_name
            )
            local = getattr(providers.get("stt"), "local", False)  # lokal Whisper — xərcsiz
            await log_usage(session, update.effective_user.id, "stt",
                            cost=0 if local else stt_cost(duration))
            await session.commit()
    except Exception:  # noqa: BLE001 — usage logu kritik deyil
        pass

    log.info(
        "voice_transcribed", user_id=update.effective_user.id, chars=len(transcript),
        audio_sec=getattr(voice, "duration", 0), stt_sec=stt_sec,
    )
    if is_journal_reply(update.message, context.bot.id):
        await _save_journal_reply(
            update, transcript, NoteSource.voice, prefix=f"🎙 _{transcript}_\n\n"
        )
        return
    await _run_agent(
        update, transcript, NoteSource.voice,
        prefix=f"🎙 _{transcript}_\n\n", input_is_voice=True,
    )


def _note_line(note) -> str:
    icon = "🎙" if note.source == NoteSource.voice else "📝"
    body = (note.summary or note.cleaned_text or note.raw_text or "")
    body = md(body[:70] + ("…" if len(body) > 70 else ""))
    pin = "📌 " if note.pinned else ""
    cat = f" · _{md_in(note.category)}_" if note.category else ""
    return f"{pin}#{note.id} {icon} {body}{cat}"


async def _build_list_view(session, uid: int, *, pinned_only: bool = False):
    """(mətn, klaviatura) qaytarır — hər qeyddə ☆/📌 (pin) + 🗑 (sil) düyməsi. Qeyd yoxdursa (None, None)."""
    notes = await list_notes(session, uid, limit=10, pinned_only=pinned_only)
    if not notes:
        return None, None
    header = "📌 *Sabitlənmiş qeydlər:*\n" if pinned_only else "🗒 *Son qeydlər:*\n"
    lines = [header] + [_note_line(n) for n in notes]
    ns = "lp" if pinned_only else "ln"
    rows = []
    for n in notes:
        pin_lbl = ("📌 " if n.pinned else "☆ ") + f"#{n.id}"
        rows.append([
            InlineKeyboardButton(pin_lbl, callback_data=f"{ns}:pin:{n.id}"),
            InlineKeyboardButton(f"🗑 #{n.id}", callback_data=f"{ns}:del:{n.id}"),
        ])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # /list <kateqoriya>  və ya  /list #tag  → filtr (mətn); arqumentsiz → düymələrlə.
    arg = " ".join(context.args).strip() if context.args else ""
    uid = update.effective_user.id
    category = tag = None
    if arg.startswith("#"):
        tag = arg[1:].strip().lower()
    elif arg:
        category = arg.lower()

    if category or tag:
        async with SessionLocal() as session:
            notes = await list_notes(session, uid, limit=10, category=category, tag=tag)
        if not notes:
            flt = f"#{tag}" if tag else category
            await update.message.reply_text(f"📭 '{flt}' üzrə qeyd tapılmadı.")
            return
        header = (
            f"🗒 *#{md_in(tag)}* üzrə qeydlər:\n" if tag
            else f"🗒 *{md_in(category)}* qeydləri:\n"
        )
        lines = [header] + [_note_line(n) for n in notes]
        await update.message.reply_markdown("\n".join(lines))
        return

    async with SessionLocal() as session:
        text, kb = await _build_list_view(session, uid)
    if text is None:
        await update.message.reply_text("📭 Hələ qeyd yoxdur. Mətn və ya səs göndər.")
        return
    await update.message.reply_markdown(text, reply_markup=kb)


async def pinned_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        text, kb = await _build_list_view(session, update.effective_user.id, pinned_only=True)
    if text is None:
        await update.message.reply_text(
            "📌 Sabitlənmiş qeyd yoxdur. /list-də ☆ düyməsi ilə qeyd sabitlə."
        )
        return
    await update.message.reply_markdown(text, reply_markup=kb)


async def related_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/related <id> — qeydlə əlaqəli qeydlər (saxlanmış linklər + vektor qonşuları)."""
    arg = (context.args[0] if context.args else "").strip().lstrip("#")
    if not arg.isdigit():
        await update.message.reply_text("İstifadə: /related <qeyd id> (məs: /related 12)")
        return
    note_id = int(arg)
    uid = update.effective_user.id
    async with SessionLocal() as session:
        note = await get_note(session, note_id)
        if note is None or note.user_id != uid:
            await update.message.reply_text(f"🤷 #{note_id} nömrəli qeyd tapılmadı.")
            return
        embedder = providers.get("embed") if providers.has("embed") else None
        hits = await find_related(
            session, uid, note, k=5, max_distance=related_threshold(embedder)
        )

    if not hits:
        await update.message.reply_text(f"🧩 #{note_id} üçün əlaqəli qeyd tapılmadı.")
        return
    lines = [f"🧩 *#{note_id}* ilə əlaqəli qeydlər:\n"]
    lines += [f"{_note_line(n)} · {round(score * 100)}%" for n, score in hits]
    await update.message.reply_markdown("\n".join(lines))


def _parse_search_args(args: list[str]) -> tuple[str, str | None, str | None]:
    """/search arqumentlərindən sorğunu + `cat:<kat>` + `#tag` filtrlərini ayır."""
    category = tag = None
    query_parts: list[str] = []
    for tok in args or []:
        low = tok.lower()
        if low.startswith("cat:"):
            category = low[4:] or None
        elif tok.startswith("#") and len(tok) > 1:
            tag = tok[1:].lower()
        else:
            query_parts.append(tok)
    return " ".join(query_parts).strip(), category, tag


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, category, tag = _parse_search_args(context.args or [])
    if not query:
        await update.message.reply_text(
            "İstifadə: /search <söz>  ·  filtr: /search <söz> cat:iş  və ya  /search <söz> #tag"
        )
        return
    if not providers.has("embed"):
        await update.message.reply_text("🔎 Axtarış deaktivdir (OPENAI_API_KEY yoxdur).")
        return

    async with SessionLocal() as session:
        embedding = await providers.get("embed").embed_one(query)
        hits = await hybrid_search_notes(
            session, update.effective_user.id, embedding, query, k=5,
            category=category, tag=tag,
        )

    if not hits:
        flt = (f" · {category}" if category else "") + (f" · #{tag}" if tag else "")
        await update.message.reply_text(f"🔎 '{query}'{flt} üzrə nəticə tapılmadı.")
        return

    lines = [f"🔎 *'{md_in(query)}'* üzrə nəticələr:\n"]
    for note, dist in hits:
        icon = "🎙" if note.source == NoteSource.voice else "📝"
        body = note.summary or note.cleaned_text or note.raw_text
        body = md(body[:70] + ("…" if len(body) > 70 else ""))
        pct = round(max(0.0, 1.0 - dist) * 100)
        lines.append(f"#{note.id} {icon} {body} · {pct}%")
    await update.message.reply_markdown("\n".join(lines))


async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        tasks = await list_open_tasks(session, update.effective_user.id, limit=30)

    if not tasks:
        await update.message.reply_text(
            "✅ Açıq tapşırıq yoxdur. Yeni əlavə etmək üçün sadəcə yaz "
            "(məs: «hesabatı bitirmək tapşırığı əlavə et»)."
        )
        return

    now = now_utc()
    lines = ["📋 *Açıq tapşırıqlar:*\n"]
    for t in tasks:
        suffix = ""
        if t.due_at is not None:
            overdue = t.due_at <= now
            when = fmt_local(t.due_at, with_weekday=False)
            suffix = f" · ⚠️ gecikib ({when})" if overdue else f" · ⏳ {when}"
        rep = " 🔁" if t.recur else ""
        lines.append(f"#{t.id} — {md(t.title)}{suffix}{rep}")
    lines.append("\n_Bağlamaq üçün:_ /done <id>")
    await update.message.reply_markdown("\n".join(lines))


async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    arg = (context.args[0] if context.args else "").strip()
    if not arg.isdigit():
        await update.message.reply_text("İstifadə: /done <tapşırıq id> (məs: /done 3)")
        return
    task_id = int(arg)
    async with SessionLocal() as session:
        task = await complete_task(session, update.effective_user.id, task_id)
        await session.commit()
    if task is None:
        await update.message.reply_text(f"🤷 #{task_id} nömrəli açıq tapşırıq tapılmadı.")
        return
    extra = " · 🔁 növbəti təkrar yaradıldı" if task.recur else ""
    await update.message.reply_text(f"✅ Tapşırıq #{task.id} bağlandı: «{task.title}»{extra}")


async def remind_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        pending = await list_pending(session, update.effective_user.id, limit=20)

    if not pending:
        await update.message.reply_text(
            "⏰ Gələn xatırlatma yoxdur. Qurmaq üçün sadəcə yaz "
            "(məs: «2 saatdan sonra su içməyi xatırlat»)."
        )
        return

    lines = ["⏰ *Gələn xatırlatmalar:*\n"]
    for r in pending:
        rep = " 🔁" if r.recur else ""
        lines.append(f"#{r.id} · {fmt_local(r.remind_at)} — {md(r.text)}{rep}")
    await update.message.reply_markdown("\n".join(lines))


_KIND_LABELS = {
    "llm": "🧠 LLM",
    "embed": "🔎 Embedding",
    "stt": "🎙 STT",
    "tts": "🔊 TTS",
    "search": "🌐 Search",
}


def _sum_tokens(totals: dict) -> int:
    return sum(tok for tok, _ in totals.values())


def _sum_cost(totals: dict) -> Decimal:
    return sum((cost for _, cost in totals.values()), Decimal("0"))


_BUDGET_LABELS = {
    "ok": "✅ normal",
    "warn": "⚠️ limitə yaxındır",
    "over": "🔻 soft rejim (Sonnet + səsli cavab söndürülü)",
}


def _budget_line(status) -> str:
    if status.state == "off":
        return "💰 *Aylıq büdcə:* limit yoxdur (`MONTHLY_BUDGET_USD`)"
    return (
        f"💰 *Aylıq büdcə:* ~${status.spent:.2f} / ${status.limit:.2f} "
        f"({status.pct}%) — {_BUDGET_LABELS[status.state]}"
    )


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    local = now_local()
    today_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async with SessionLocal() as session:
        today = await usage_totals(session, uid, today_start)
        month = await usage_totals(session, uid, month_start)
        msgs_today = await count_messages(session, uid, "user", today_start)
        msgs_month = await count_messages(session, uid, "user", month_start)

    lines = ["📊 *İstifadə statistikası*\n"]
    lines.append(
        f"*Bu gün:* {msgs_today} mesaj · {_sum_tokens(today)} token · "
        f"~${_sum_cost(today):.4f}"
    )
    lines.append(
        f"*Bu ay:* {msgs_month} mesaj · {_sum_tokens(month)} token · "
        f"~${_sum_cost(month):.4f}"
    )
    lines.append(_budget_line(status_for(_sum_cost(month))))
    if month:
        lines.append("\n_Növ üzrə (bu ay):_")
        for kind, (tok, cost) in sorted(month.items()):
            label = _KIND_LABELS.get(kind, kind)
            lines.append(f"  {label}: {tok} token · ~${cost:.4f}")
    if settings.resolved_llm_backend == "subscription":
        lines.append("\n_Abunə rejimi: real ödəniş yoxdur — rəqəmlər API ekvivalentidir._")
    lines.append("\n_Qiymətlər təxminidir._")
    await update.message.reply_markdown("\n".join(lines))


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    async with SessionLocal() as session:
        notes = await all_notes(session, uid)

    if not notes:
        await update.message.reply_text("📭 Export üçün qeyd yoxdur.")
        return

    lines = [
        f"# Second Brain — export ({fmt_local(now_local(), with_weekday=False)})",
        f"Ümumi qeyd: {len(notes)}",
        "",
    ]
    for n in notes:
        when = fmt_local(n.created_at, with_weekday=False)
        lines.append(f"## #{n.id} · {when} · {n.source.value}")
        if n.category:
            lines.append(f"**Kateqoriya:** {n.category}")
        if n.tags:
            lines.append(f"**Tag:** {', '.join(n.tags)}")
        lines.append("")
        lines.append(n.cleaned_text or n.raw_text)
        lines.append("")
    content = "\n".join(lines)

    fd, path = tempfile.mkstemp(prefix="second_brain_", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        fname = f"second_brain_{now_local().strftime('%Y%m%d')}.md"
        with open(path, "rb") as f:
            await update.message.reply_document(
                document=f, filename=fname, caption=f"🗂 {len(notes)} qeyd export edildi."
            )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    arg = (context.args[0] if context.args else "").strip().lower()

    if arg == "all":
        async with SessionLocal() as session:
            count = len(await all_notes(session, uid))
        if not count:
            await update.message.reply_text("📭 Silinəcək qeyd yoxdur.")
            return
        kb = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(f"⚠️ Bəli, {count} qeydi sil", callback_data="del:all"),
                InlineKeyboardButton("İmtina", callback_data="del:cancel"),
            ]]
        )
        await update.message.reply_text(
            f"⚠️ BÜTÜN {count} qeydini silmək istəyirsən? Bu geri qaytarıla bilməz.",
            reply_markup=kb,
        )
        return

    if not arg.isdigit():
        await update.message.reply_text("İstifadə: /delete <id>  və ya  /delete all")
        return

    note_id = int(arg)
    async with SessionLocal() as session:
        note = await get_note(session, note_id)
    if note is None or note.user_id != uid:
        await update.message.reply_text(f"🤷 #{note_id} nömrəli qeyd tapılmadı.")
        return

    preview = (note.summary or note.cleaned_text or note.raw_text)[:120]
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🗑 Sil", callback_data=f"del:one:{note_id}"),
            InlineKeyboardButton("İmtina", callback_data="del:cancel"),
        ]]
    )
    await update.message.reply_text(f"Silinsin?\n#{note_id}: {preview}", reply_markup=kb)


async def edit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/edit <id> <yeni mətn> — qeydi yenidən təmizləyib re-embed edir."""
    args = context.args or []
    if len(args) < 2 or not args[0].isdigit():
        await update.message.reply_text("İstifadə: /edit <id> <yeni mətn>")
        return
    if not await _rate_ok(update):
        return

    note_id = int(args[0])
    new_text = " ".join(args[1:]).strip()
    uid = update.effective_user.id

    async with SessionLocal() as session:
        note = await get_note(session, note_id)
        if note is None or note.user_id != uid:
            await update.message.reply_text(f"🤷 #{note_id} nömrəli qeyd tapılmadı.")
            return
        await update.message.chat.send_action("typing")
        llm = providers.get("llm") if providers.has("llm") else None
        embedder = providers.get("embed") if providers.has("embed") else None
        await recapture_note(session, note, new_text, llm=llm, embedder=embedder)
        await session.commit()
        cat, tags = note.category, list(note.tags or [])

    reply = f"✏️ Qeyd #{note_id} yeniləndi."
    if cat:
        reply += f"\n🏷 {cat}"
    if tags:
        reply += f"\n#" + " #".join(tags)
    await update.message.reply_text(reply)


def _settings_text(s: dict) -> str:
    enabled = s.get("briefing_enabled", True)
    hour = int(s.get("briefing_hour", 8))
    status = "açıq 🔔" if enabled else "bağlı 🔕"
    digest = "açıq 📊" if s.get("digest_enabled", False) else "bağlı 🔕"
    evening = "açıq 🌙" if s.get("evening_enabled", True) else "bağlı 🔕"
    evening_hour = int(s.get("evening_hour", 22))
    return (
        "⚙️ *Ayarlar*\n\n"
        f"Səhər brifinqi: *{status}*\n"
        f"Saat: *{hour:02d}:00* (Asia/Baku)\n"
        f"Həftəlik icmal (B.e.): *{digest}*\n"
        f"Axşam yekunu ({evening_hour:02d}:00): *{evening}*\n\n"
        "Dəyişmək üçün düymələrdən istifadə et:"
    )


def _settings_keyboard(s: dict) -> InlineKeyboardMarkup:
    enabled = s.get("briefing_enabled", True)
    hour = int(s.get("briefing_hour", 8))
    digest_on = s.get("digest_enabled", False)
    toggle = "🔕 Brifinqi söndür" if enabled else "🔔 Brifinqi aç"
    digest_btn = "🔕 Həftəlik icmalı söndür" if digest_on else "📊 Həftəlik icmalı aç"
    evening_btn = (
        "🔕 Axşam yekununu söndür" if s.get("evening_enabled", True) else "🌙 Axşam yekununu aç"
    )
    rows = [
        [InlineKeyboardButton(toggle, callback_data="set:toggle")],
        [InlineKeyboardButton(digest_btn, callback_data="set:digest")],
        [InlineKeyboardButton(evening_btn, callback_data="set:evening")],
    ]
    hours = [6, 7, 8, 9, 10, 21]
    btns = [
        InlineKeyboardButton(("• " if h == hour else "") + f"{h:02d}:00", callback_data=f"set:hour:{h}")
        for h in hours
    ]
    rows.append(btns[:3])
    rows.append(btns[3:])
    return InlineKeyboardMarkup(rows)


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        user = await get_or_create_user(
            session, update.effective_user.id, name=update.effective_user.full_name
        )
        await session.commit()
        s = dict(user.settings or {})
    await update.message.reply_markdown(_settings_text(s), reply_markup=_settings_keyboard(s))


def _voice_status_text(s: dict) -> str:
    enabled, name = _voice_settings(s)
    status = "açıq 🔊" if enabled else "bağlı 🔇"
    mirror = "açıq 🎙️" if s.get("voice_mirror", True) else "bağlı 🔇"
    label = _VOICE_LABELS.get(name, name)
    return (
        "🔊 *Səsli cavab*\n\n"
        f"Həmişə səslə cavab: *{status}*\n"
        f"Səslə yazanda səslə cavab (mirror): *{mirror}*\n"
        f"Səs: *{label}*\n\n"
        "İdarə:\n"
        "• /voice — aç/söndür\n"
        "• /voice mirror — «səslə yaz → səslə cavab» aç/söndür\n"
        "• /voice babek | banu — səsi seç\n"
        "• /voice test — nümunə səs eşit"
    )


async def voice_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not providers.has("tts"):
        await update.message.reply_text(
            "🔇 Səsli cavab deaktivdir (AZURE_SPEECH_KEY/REGION yoxdur)."
        )
        return

    arg = (context.args[0].strip().lower() if context.args else "")

    # /voice test — cari səslə nümunə göndər (ayarı dəyişmədən).
    if arg == "test":
        async with SessionLocal() as session:
            user = await get_or_create_user(session, uid, name=update.effective_user.full_name)
            await session.commit()
            _, name = _voice_settings(user.settings)
        await _speak_reply(
            update, "Salam Samir, bu Azərbaycan dilində səsli cavab nümunəsidir.", name
        )
        return

    async with SessionLocal() as session:
        user = await get_or_create_user(session, uid, name=update.effective_user.full_name)
        s = dict(user.settings or {})

        if arg in AZ_VOICES:  # səs seçimi + səsli cavabı aç
            s["voice_name"] = AZ_VOICES[arg]
            s["voice_reply"] = True
        elif arg == "mirror":  # «səslə yaz → səslə cavab» toggle
            s["voice_mirror"] = not s.get("voice_mirror", True)
        elif arg == "on":
            s["voice_reply"] = True
        elif arg == "off":
            s["voice_reply"] = False
        elif arg == "":  # arqumentsiz → toggle
            s["voice_reply"] = not s.get("voice_reply", False)
        else:
            await update.message.reply_text(
                "İstifadə: /voice (aç/söndür) · /voice mirror · /voice babek|banu · /voice test"
            )
            return

        s = await update_settings(session, uid, s)
        await session.commit()

    await update.message.reply_markdown(_voice_status_text(s))


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    uid = update.effective_user.id

    # CallbackQueryHandler-də user filtri yoxdur — allowlist-i burada yoxla.
    if settings.allowed_ids and uid not in settings.allowed_ids:
        log.warning("unauthorized_callback", user_id=uid)
        return

    if data == "del:cancel":
        await q.edit_message_text("İmtina edildi.")
        return

    if data.startswith("mc:"):
        await _on_cleanup_callback(q, context, uid, data.split(":"))
        return

    if data.startswith("mt:"):
        await _on_trash_callback(q, context, uid, data.split(":"))
        return

    if data.startswith("rem:"):
        parts = data.split(":")
        action = parts[1]
        rid = int(parts[2])
        async with SessionLocal() as session:
            reminder = await session.get(Reminder, rid)
            if reminder is None or reminder.user_id != uid:
                await q.edit_message_text("🤷 Xatırlatma tapılmadı.")
                return
            text = reminder.text
            if action == "snooze":
                minutes = int(parts[3])
                when = now_utc() + timedelta(minutes=minutes)
                await create_reminder(session, uid, text, when)
                await session.commit()
                await q.edit_message_text(
                    f"😴 {minutes} dəq sonra yenidən xatırladacağam: «{text}»"
                )
            elif action == "done":
                if reminder.recur:  # təkrarlanmanı dayandır
                    reminder.recur = None
                    reminder.sent = True
                    await session.commit()
                    await q.edit_message_text(f"✅ Təkrarlanma dayandırıldı: «{text}»")
                else:
                    await q.edit_message_text(f"✅ Bağlandı: «{text}»")
        return

    # /list · /pinned düymələri: sil / sabitlə (toggle) → siyahını yenilə.
    if data.startswith("ln:") or data.startswith("lp:"):
        ns, action, sid = data.split(":")
        nid = int(sid)
        pinned_view = ns == "lp"
        async with SessionLocal() as session:
            if action == "del":
                await delete_note(session, uid, nid)
            elif action == "pin":
                await set_pinned(session, uid, nid)  # toggle
            await session.commit()
            text, kb = await _build_list_view(session, uid, pinned_only=pinned_view)
        if text is None:
            msg = "📌 Sabitlənmiş qeyd qalmadı." if pinned_view else "📭 Qeyd qalmadı."
            await q.edit_message_text(msg)
        else:
            await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        return

    if data.startswith("del:one:"):
        note_id = int(data.split(":")[2])
        async with SessionLocal() as session:
            note = await delete_note(session, uid, note_id)
            await session.commit()
        if note is None:
            await q.edit_message_text(f"🤷 #{note_id} tapılmadı.")
        else:
            await q.edit_message_text(f"🗑 Qeyd #{note_id} silindi.")
        return

    if data == "del:all":
        async with SessionLocal() as session:
            n = await delete_all_notes(session, uid)
            await session.commit()
        await q.edit_message_text(f"🗑 {n} qeyd silindi.")
        return

    if data.startswith("set:"):
        parts = data.split(":")
        async with SessionLocal() as session:
            user = await get_or_create_user(session, uid)
            s = dict(user.settings or {})
            if parts[1] == "toggle":
                s["briefing_enabled"] = not s.get("briefing_enabled", True)
            elif parts[1] == "digest":
                s["digest_enabled"] = not s.get("digest_enabled", False)
            elif parts[1] == "evening":
                s["evening_enabled"] = not s.get("evening_enabled", True)
            elif parts[1] == "hour":
                s["briefing_hour"] = int(parts[2])
            s = await update_settings(session, uid, s)
            await session.commit()
        await q.edit_message_text(
            _settings_text(s), parse_mode="Markdown", reply_markup=_settings_keyboard(s)
        )
        return


MAIL_NOT_CONFIGURED = (
    "📭 E-poçt qoşulmayıb. .env-də EMAIL_IMAP_HOST, EMAIL_ADDRESS, EMAIL_PASSWORD doldur "
    "(Gmail üçün App Password) və botu yenidən başlat."
)
CLEANUP_SAMPLE = 10  # təmizlik siyahısında göstərilən son reklam məktubları


def _cleanup_text(total: int, sample) -> str:
    lines = [f"🧹 Inbox-da {total} reklam məktubu var (Gmail-in «Reklamlar» bölməsi).", ""]
    if total > len(sample):
        lines.append(f"Son {len(sample)} məktub:")
    for m in sample:
        subject = m.subject if len(m.subject) <= 70 else m.subject[:69] + "…"
        lines.append(f"• {short_sender(m.sender)} — {subject}")
    lines += [
        "",
        "«Hamısını arxivlə» onları yalnız Inbox-dan çıxarır: məktublar Gmail-də qalır, "
        "heç nə silinmir. Ulduzlu məktublara toxunulmur.",
    ]
    return "\n".join(lines)


async def _send_cleanup(bot, uid: int) -> None:
    """Reklam məktublarının siyahısı + «Hamısını arxivlə» (/mail təmizlə, axşam yekunu)."""
    if not providers.has("email"):
        await bot.send_message(uid, MAIL_NOT_CONFIGURED)
        return
    if not is_mail_owner(uid):
        await bot.send_message(uid, "🔒 Poçt təmizliyi yalnız poçt qutusunun sahibi üçündür.")
        return
    try:
        ids, sample = await providers.get("email").promotions(limit=CLEANUP_SAMPLE)
    except Exception as exc:  # noqa: BLE001
        log.error("mail_cleanup_list_failed", error=str(exc))
        await bot.send_message(uid, f"📭 Reklam məktublarını almaq olmadı: {exc}")
        return
    if not ids:
        await bot.send_message(uid, "✨ Inbox-da reklam məktubu yoxdur.")
        return
    # Düymə bu siyahıya bağlıdır: köhnə mesajın düyməsi yeni siyahını arxivləməsin.
    key = now_utc().strftime("%m%d%H%M%S")
    async with SessionLocal() as session:
        await get_or_create_user(session, uid)
        batch = {"key": key, "ids": ids, "archived": []}
        await update_settings(session, uid, {"mail_cleanup": batch})
        await session.commit()
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"📦 Hamısını arxivlə ({len(ids)})", callback_data=f"mc:arch:{key}"),
        InlineKeyboardButton("İmtina", callback_data="mc:cancel"),
    ]])
    await bot.send_message(uid, _cleanup_text(len(ids), sample), reply_markup=keyboard)


async def _on_cleanup_callback(q, context, uid: int, parts: list[str]) -> None:
    """mc:show · mc:cancel · mc:arch:<key> · mc:undo:<key> — poçt təmizliyi düymələri."""
    action = parts[1] if len(parts) > 1 else ""
    if action == "show":
        await _send_cleanup(context.bot, uid)
        return
    if action == "cancel":
        await q.edit_message_text("İmtina edildi — məktublara toxunulmadı.")
        return
    if action not in ("arch", "undo") or not (providers.has("email") and is_mail_owner(uid)):
        return
    key = parts[2] if len(parts) > 2 else ""
    async with SessionLocal() as session:
        user = await get_or_create_user(session, uid)
        batch = dict((user.settings or {}).get("mail_cleanup") or {})
    if not key or batch.get("key") != key:
        await q.edit_message_text("⌛ Bu siyahı köhnəlib. Yenisi üçün: /mail təmizlə")
        return
    ids = batch.get("ids" if action == "arch" else "archived") or []
    if not ids:
        state = "arxivlənib" if action == "arch" else "Inbox-a qaytarılıb"
        await q.edit_message_text(f"Bu siyahı artıq {state}.")
        return

    box = providers.get("email")
    await q.edit_message_text("⏳ Arxivləyirəm…" if action == "arch" else "⏳ Inbox-a qaytarıram…")
    try:
        if action == "arch":
            archived = await box.archive(ids)
            batch.update(ids=[], archived=archived)
        else:
            restored = await box.unarchive(ids)
            batch.update(archived=[])
    except Exception as exc:  # noqa: BLE001 — siyahı dəyişmir, sonra yenidən cəhd etmək olar
        log.error("mail_cleanup_failed", action=action, error=str(exc))
        await q.edit_message_text(f"⚠️ Alınmadı: {exc}\nBir az sonra /mail təmizlə ilə yoxla.")
        return
    async with SessionLocal() as session:
        await update_settings(session, uid, {"mail_cleanup": batch})
        await session.commit()

    if action == "undo":
        log.info("mail_unarchived", count=restored)
        await q.edit_message_text(f"↩️ {restored} məktub Inbox-a qaytarıldı.")
    elif not archived:
        await q.edit_message_text("🤷 Bu məktublar artıq Inbox-da deyil, toxunulacaq heç nə yoxdur.")
    else:
        log.info("mail_archived", count=len(archived))
        await q.edit_message_text(
            f"📦 {len(archived)} məktub arxivləndi: Inbox-dan çıxdı, Gmail-də qalır.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ Geri qaytar", callback_data=f"mc:undo:{key}")]]
            ),
        )


TRASH_NOTE = (
    "Silinənlər Gmail-in Zibil qutusuna gedir — 30 gün ərzində geri qaytarmaq olar. "
    "Şəxsi («Əsas») və ulduzlu məktublara toxunulmur."
)


def _cut(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _trash_text(p: dict) -> str:
    lines = [f"🗑 Lazımsız görünən {len(p['items'])} məktub "
             f"(Claude {p['reviewed']} məktuba baxdı):", ""]
    for n, it in enumerate(p["items"], 1):
        lines.append(f"{n}. {_cut(it['from'], 22)} — {_cut(it['subject'], 45)} "
                     f"({_cut(it['reason'], 50)})")
    lines += ["", TRASH_NOTE]
    return "\n".join(lines)


def _trash_keyboard(p: dict, picking: bool = False) -> InlineKeyboardMarkup:
    key, n = p["key"], len(p["items"])
    keep_row = [InlineKeyboardButton("✋ Hamısını saxla", callback_data=f"mt:keep:{key}")]
    if not picking:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🗑 Hamısını sil ({n})", callback_data=f"mt:del:{key}"),
             InlineKeyboardButton("✏️ Seç", callback_data=f"mt:pick:{key}")],
            keep_row,
        ])
    drop = set(p.get("drop") or [])
    toggles = [
        InlineKeyboardButton(f"{'✋' if i in drop else '🗑'} {i}", callback_data=f"mt:t:{key}:{i}")
        for i in range(1, n + 1)
    ]
    rows = [toggles[i : i + 5] for i in range(0, n, 5)]
    rows.append([InlineKeyboardButton(f"🗑 Seçilənləri sil ({n - len(drop)})",
                                      callback_data=f"mt:del:{key}")])
    rows.append(keep_row)
    return InlineKeyboardMarkup(rows)


async def _send_trash_proposal(bot, uid: int, p: dict) -> None:
    if not p.get("items"):
        await bot.send_message(
            uid, f"✨ Lazımsız məktub tapılmadı (Claude {p.get('reviewed', 0)} məktuba baxdı)."
        )
        return
    await bot.send_message(uid, _trash_text(p), reply_markup=_trash_keyboard(p))


async def _review_and_send(bot, uid: int) -> None:
    """Claude ilə yeni baxış → siyahı + təsdiq düymələri (/mail sil, «Daha çox yoxla»)."""
    if not providers.has("email"):
        await bot.send_message(uid, MAIL_NOT_CONFIGURED)
        return
    if not is_mail_owner(uid):
        await bot.send_message(uid, "🔒 Məktubları yalnız poçt qutusunun sahibi silə bilər.")
        return
    if not providers.has("llm"):
        await bot.send_message(uid, "🤖 Claude qoşulmayıb — məktublara baxa bilmirəm.")
        return
    await bot.send_message(uid, "🔎 Claude məktublara baxır…")  # düyməni təkrar basmasın
    try:
        async with SessionLocal() as session:
            p = await build_proposal(session, uid, providers.get("email"), providers.get("llm"))
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        log.error("mail_review_failed", error=str(exc))
        await bot.send_message(uid, f"⚠️ Məktublara baxmaq alınmadı: {exc}")
        return
    await _send_trash_proposal(bot, uid, p)


async def _deliver_trash_proposal(update: Update, p: dict) -> None:
    """Agent alətinin hazırladığı siyahını göndər (bir dəfə)."""
    async with SessionLocal() as session:
        await update_settings(session, update.effective_user.id,
                              {"mail_trash": {**p, "deliver": False}})
        await session.commit()
    await update.message.reply_text(_trash_text(p), reply_markup=_trash_keyboard(p))


async def _on_trash_callback(q, context, uid: int, parts: list[str]) -> None:
    """mt:more · mt:show|pick|t|del|keep|undo:<key> — lazımsız məktub düymələri.

    Silmə YALNIZ buradan gedir: düyməni istifadəçinin özü basır, məktub mətni və ya Claude
    bunu edə bilməz.
    """
    action = parts[1] if len(parts) > 1 else ""
    key = parts[2] if len(parts) > 2 else ""
    if not (providers.has("email") and is_mail_owner(uid)):
        return
    if action == "more":
        await _review_and_send(context.bot, uid)
        return
    box = providers.get("email")
    async with SessionLocal() as session:
        user = await get_or_create_user(session, uid)
        s = dict(user.settings or {})
    kept = list(s.get("mail_kept") or [])
    undo = dict(s.get("mail_trash_undo") or {})

    if action == "undo":
        ids = undo.pop(key, None)
        if not ids:
            await q.edit_message_text("Bu məktublar artıq Inbox-a qaytarılıb.")
            return
        await q.edit_message_text("⏳ Inbox-a qaytarıram…")
        try:
            restored = await box.untrash(ids)
        except Exception as exc:  # noqa: BLE001
            log.error("mail_untrash_failed", error=str(exc))
            await q.edit_message_text(f"⚠️ Alınmadı: {exc}")
            return
        await _save_settings(uid, {"mail_trash_undo": undo, "mail_kept": (kept + ids)[-MAX_KEPT:]})
        log.info("mail_untrashed", count=restored)
        await q.edit_message_text(f"↩️ {restored} məktub Inbox-a qaytarıldı — bir daha "
                                  "təklif olunmayacaq.")
        return

    p = dict(s.get("mail_trash") or {})
    if not key or p.get("key") != key or not p.get("items"):
        stale = "⌛ Bu siyahı köhnəlib. Yenisi üçün: /mail sil"
        if action == "show":  # axşam yekununun düyməsi: mətnə toxunma, Reply → gündəlik ona bağlıdır
            await context.bot.send_message(uid, stale)
        elif p.get("key") != key:  # eyni siyahıda ikinci basış: nəticə və «Geri qaytar» qalsın
            await q.edit_message_text(stale)
        return
    if action == "show":
        await _send_trash_proposal(context.bot, uid, p)
        return
    if action in ("pick", "t"):
        if action == "t" and len(parts) > 3 and parts[3].isdigit():
            i = int(parts[3])
            if 1 <= i <= len(p["items"]):
                p["drop"] = sorted(set(p.get("drop") or []) ^ {i})
                await _save_settings(uid, {"mail_trash": p})
        await q.edit_message_reply_markup(reply_markup=_trash_keyboard(p, picking=True))
        return
    if action not in ("del", "keep"):
        return

    drop = set(p.get("drop") or []) if action == "del" else set(range(1, len(p["items"]) + 1))
    chosen = [it["id"] for i, it in enumerate(p["items"], 1) if i not in drop]
    keep = [it["id"] for i, it in enumerate(p["items"], 1) if i in drop]
    trashed: list[int] = []
    if chosen:
        await q.edit_message_text("⏳ Zibil qutusuna köçürürəm…")
        try:
            trashed = await box.trash(chosen)
        except Exception as exc:  # noqa: BLE001 — siyahı qalır, düyməni yenidən basmaq olar
            log.error("mail_trash_failed", error=str(exc))
            await q.edit_message_text(f"⚠️ Alınmadı: {exc}\nBir az sonra /mail sil ilə yoxla.")
            return
    if trashed:
        undo[key] = trashed
    await _save_settings(uid, {
        "mail_trash": {**p, "items": []},
        "mail_trash_undo": dict(list(undo.items())[-5:]),
        "mail_kept": (kept + keep)[-MAX_KEPT:],
    })
    rows = []
    if trashed:
        rows.append([InlineKeyboardButton("↩️ Geri qaytar", callback_data=f"mt:undo:{key}")])
    rows.append([InlineKeyboardButton("🔎 Daha çox yoxla", callback_data="mt:more")])
    if trashed:
        log.info("mail_trashed", count=len(trashed))
        text = f"🗑 {len(trashed)} məktub Zibil qutusuna köçürüldü — 30 gün geri qaytarmaq olar."
        if keep:
            text += f"\n✋ {len(keep)} məktub saxlanıldı."
    else:
        text = "✋ Saxlanıldı — bu məktublar bir daha təklif olunmayacaq."
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))


async def _save_settings(uid: int, changes: dict) -> None:
    async with SessionLocal() as session:
        await update_settings(session, uid, changes)
        await session.commit()


async def mail_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/mail — son məktublar · /mail <uid> — oxu · /mail on|off — yeni məktub bildirişi ·
    /mail təmizlə — reklamları arxivlə · /mail sil — lazımsız məktubları sil (təsdiqlə)."""
    if not providers.has("email"):
        await update.message.reply_text(MAIL_NOT_CONFIGURED)
        return
    uid = update.effective_user.id
    arg = (context.args[0].strip().lower() if context.args else "")

    if arg in ("təmizlə", "temizle", "clean"):
        await update.message.chat.send_action("typing")
        await _send_cleanup(context.bot, uid)
        return
    if arg in ("sil", "delete"):
        await update.message.chat.send_action("typing")
        await _review_and_send(context.bot, uid)
        return

    if arg in ("on", "off"):
        async with SessionLocal() as session:
            await get_or_create_user(session, uid, name=update.effective_user.full_name)
            await update_settings(session, uid, {"email_notify": arg == "on"})
            await session.commit()
        state = "açıldı 🔔" if arg == "on" else "söndürüldü 🔕"
        await update.message.reply_text(f"📬 Yeni məktub bildirişi {state}.")
        return

    box = providers.get("email")
    await update.message.chat.send_action("typing")
    try:
        if arg.isdigit():
            m = await box.get(int(arg))
            if m is None:
                await update.message.reply_text(f"🤷 uid={arg} məktub tapılmadı.")
                return
            when = fmt_local(m.date, with_weekday=False) if m.date else "?"
            body = m.body[:MAX_BODY_CHARS // 2] + ("…" if len(m.body) > MAX_BODY_CHARS // 2 else "")
            await update.message.reply_text(
                f"📧 {m.subject}\nKimdən: {m.sender}\nTarix: {when}\n\n{body or '(mətn yoxdur)'}"
            )
            return
        mails = await box.recent(limit=10)
    except Exception as exc:  # noqa: BLE001
        log.error("mail_cmd_failed", error=str(exc))
        await update.message.reply_text(f"📭 E-poçta qoşulmaq olmadı: {exc}")
        return

    if not mails:
        await update.message.reply_text("📭 Qovluqda məktub yoxdur.")
        return
    lines = ["📬 Son məktublar (● = oxunmamış):"]
    for m in mails:
        when = fmt_local(m.date, with_weekday=False) if m.date else "?"
        dot = "● " if m.unread else ""
        lines.append(f"{dot}{m.uid} · {when} · {short_sender(m.sender)} — {m.subject}")
    lines.append("\nOxumaq: /mail <uid> · Bildiriş: /mail on | /mail off")
    lines.append("Sual da verə bilərsən: «Əlidən gələn son məktubu xülasə et».")
    await update.message.reply_text("\n".join(lines))


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Qlobal xəta handler-i — istifadəçi cavabsız qalmasın, səbəb loglansın."""
    err = context.error
    if isinstance(err, Conflict):
        log.error(
            "telegram_conflict",
            hint="Eyni TELEGRAM_BOT_TOKEN ilə başqa instans işləyir (VPS? Mac?) — birini dayandır.",
        )
        return
    log.error(
        "handler_error",
        error=repr(err),
        trace="".join(traceback.format_exception(err)) if err else None,
    )
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Gözlənilməz xəta baş verdi — bir az sonra yenidən cəhd et."
            )
        except Exception:  # noqa: BLE001
            pass


async def unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    log.warning("unauthorized_access", user_id=user.id, username=user.username)
    await update.message.reply_text(
        f"⛔️ Bu şəxsi botdur — sənin girişin yoxdur.\nSənin ID: {user.id}"
    )
