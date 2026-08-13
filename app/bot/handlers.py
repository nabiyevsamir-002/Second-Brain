"""Telegram handler-ları (Phase 2 — tool-using agent + RAG).

Mətn/səs → agent niyyəti routing edir (save_note / search_notes) → cavab.
/search RAG axtarış. /list son qeydlər. Agent yoxdursa xam saxlamaya fallback.
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.logging_conf import get_logger
from app.models import NoteSource
from app.pricing import stt_cost
from app.providers.registry import providers
from app.repositories.messages import add_message, count_messages, get_recent_messages
from app.repositories.notes import (
    all_notes,
    delete_all_notes,
    delete_note,
    get_note,
    list_notes,
    search_notes_by_vector,
)
from app.repositories.reminders import list_pending
from app.repositories.tasks import complete_task, list_open_tasks
from app.repositories.usage import log_usage, usage_totals
from app.repositories.users import get_or_create_user, update_settings
from app.services.ingest_service import ingest_document, ingest_url
from app.services.notes_service import capture_note
from app.timeutils import fmt_local, now_local, now_utc

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
    "/tasks — açıq tapşırıqlar\n"
    "/done <id> — tapşırığı bağla\n"
    "/remind — gələn xatırlatmalar\n"
    "/stats — istifadə və xərc\n"
    "/export — qeydləri fayl kimi yüklə\n"
    "/delete <id> — qeydi sil (/delete all = hamısı)\n"
    "/settings — brifinq ayarları\n"
    "/id — Telegram ID\n\n"
    "*Nə göndərə bilərsən:*\n"
    "• 📝 mətn / 🎙 səs → qeyd, sual, tapşırıq və ya xatırlatma\n"
    "• ⏰ «sabah 9-da həkimə zəng etməyi xatırlat» → xatırlatma qururam\n"
    "• 📋 «hesabatı bitirmək tapşırığı əlavə et» → tapşırıq yaradıram\n"
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

    # STT xərcini logla (audio uzunluğuna görə).
    try:
        duration = getattr(voice, "duration", 0) or 0
        async with SessionLocal() as session:
            await get_or_create_user(
                session, update.effective_user.id, name=update.effective_user.full_name
            )
            await log_usage(session, update.effective_user.id, "stt", cost=stt_cost(duration))
            await session.commit()
    except Exception:  # noqa: BLE001 — usage logu kritik deyil
        pass

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
        lines.append(f"#{t.id} — {t.title}{suffix}")
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
    await update.message.reply_text(f"✅ Tapşırıq #{task.id} bağlandı: «{task.title}»")


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
        lines.append(f"#{r.id} · {fmt_local(r.remind_at)} — {r.text}")
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
    if month:
        lines.append("\n_Növ üzrə (bu ay):_")
        for kind, (tok, cost) in sorted(month.items()):
            label = _KIND_LABELS.get(kind, kind)
            lines.append(f"  {label}: {tok} token · ~${cost:.4f}")
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


def _settings_text(s: dict) -> str:
    enabled = s.get("briefing_enabled", True)
    hour = int(s.get("briefing_hour", 8))
    status = "açıq 🔔" if enabled else "bağlı 🔕"
    return (
        "⚙️ *Ayarlar*\n\n"
        f"Səhər brifinqi: *{status}*\n"
        f"Saat: *{hour:02d}:00* (Asia/Baku)\n\n"
        "Dəyişmək üçün düymələrdən istifadə et:"
    )


def _settings_keyboard(s: dict) -> InlineKeyboardMarkup:
    enabled = s.get("briefing_enabled", True)
    hour = int(s.get("briefing_hour", 8))
    toggle = "🔕 Brifinqi söndür" if enabled else "🔔 Brifinqi aç"
    rows = [[InlineKeyboardButton(toggle, callback_data="set:toggle")]]
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


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    uid = update.effective_user.id

    if data == "del:cancel":
        await q.edit_message_text("İmtina edildi.")
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
            elif parts[1] == "hour":
                s["briefing_hour"] = int(parts[2])
            s = await update_settings(session, uid, s)
            await session.commit()
        await q.edit_message_text(
            _settings_text(s), parse_mode="Markdown", reply_markup=_settings_keyboard(s)
        )
        return


async def unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    log.warning("unauthorized_access", user_id=user.id, username=user.username)
    await update.message.reply_text(
        f"⛔️ Bu şəxsi botdur — sənin girişin yoxdur.\nSənin ID: {user.id}"
    )
