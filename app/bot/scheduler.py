"""Proaktiv scheduler (Phase 4) — PTB JobQueue əsasında.

İki iş:
  • deliver_due_reminders — hər 60 san: vaxtı çatmış xatırlatmaları çatdırır.
  • morning_briefing — hər gün səhər: günün tapşırıq/xatırlatma/qeyd icmalı.

Gecə pg_dump backup host cron ilə işləyir (scripts/backup.sh) — burada deyil.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes

from app.config import settings
from app.db import SessionLocal
from app.logging_conf import get_logger
from app.models import TaskStatus
from app.repositories.notes import category_counts_since, count_notes_since
from app.repositories.reminders import (
    due_reminders,
    reminders_between,
    reschedule_or_mark_sent,
)
from app.repositories.tasks import list_open_tasks
from app.repositories.users import get_user, update_settings
from app.timeutils import fmt_local, now_local, now_utc

log = get_logger("scheduler")

REMINDER_INTERVAL_SEC = 60
BRIEFING_DEFAULT_HOUR = 8  # local (Asia/Baku) — istifadəçi /settings ilə dəyişə bilər
DIGEST_DEFAULT_WEEKDAY = 0  # Bazar ertəsi (0=Mon … 6=Sun) — həftəlik icmal günü


def _reminder_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    """Snooze (təxirə sal) + bağla düymələri."""
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("😴 10 dəq", callback_data=f"rem:snooze:{reminder_id}:10"),
            InlineKeyboardButton("😴 1 saat", callback_data=f"rem:snooze:{reminder_id}:60"),
            InlineKeyboardButton("✅ Bağla", callback_data=f"rem:done:{reminder_id}"),
        ]]
    )


async def deliver_due_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vaxtı çatmış, göndərilməmiş xatırlatmaları Telegram-a çatdırır.

    Təkrarlanan (recur) xatırlatma çatdırıldıqdan sonra növbəti vaxta sürüşür.
    Hər mesajda snooze/bağla düymələri olur.
    """
    now = now_utc()
    async with SessionLocal() as session:
        due = await due_reminders(session, now)
        for r in due:
            try:
                suffix = " 🔁" if r.recur else ""
                await context.bot.send_message(
                    chat_id=r.user_id,
                    text=f"⏰ Xatırlatma: {r.text}{suffix}",
                    reply_markup=_reminder_keyboard(r.id),
                )
                await reschedule_or_mark_sent(session, r, now)
                log.info(
                    "reminder_delivered", reminder_id=r.id, user_id=r.user_id, recur=r.recur
                )
            except Exception as exc:  # noqa: BLE001 — göndərmə uğursuzdursa növbəti turda təkrar
                log.warning(
                    "reminder_delivery_failed", reminder_id=r.id, error=str(exc)
                )
        await session.commit()


def _local_day_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """Verilmiş local anın gün başlanğıcı və sonu (tz-aware)."""
    start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


async def _build_briefing(session, user_id: int) -> str:
    local = now_local()
    day_start, day_end = _local_day_bounds(local)
    now = now_utc()

    user = await get_user(session, user_id)
    name = (user.name.split()[0] if user and user.name else None)
    greet = f"☀️ Sabahın xeyir, {name}!" if name else "☀️ Sabahın xeyir!"
    header = f"{greet}\n📅 {fmt_local(local)}\n"

    lines = [header]

    tasks = await list_open_tasks(session, user_id, limit=10)
    if tasks:
        lines.append("📋 *Açıq tapşırıqlar:*")
        for t in tasks:
            mark = ""
            if t.due_at is not None:
                overdue = t.due_at <= now and t.status == TaskStatus.open
                mark = f" · ⚠️ gecikib ({fmt_local(t.due_at, with_weekday=False)})" if overdue \
                    else f" · ⏳ {fmt_local(t.due_at, with_weekday=False)}"
            lines.append(f"  #{t.id} {t.title}{mark}")
        lines.append("")

    todays = await reminders_between(session, user_id, day_start, day_end)
    if todays:
        lines.append("⏰ *Bugünkü xatırlatmalar:*")
        for r in todays:
            lines.append(f"  • {fmt_local(r.remind_at, with_weekday=False)[11:]} — {r.text}")
        lines.append("")

    n_recent = await count_notes_since(session, user_id, now - timedelta(hours=24))
    if n_recent:
        lines.append(f"🗒 Son 24 saatda {n_recent} qeyd əlavə etdin.")

    if not tasks and not todays and not n_recent:
        lines.append("Bu gün üçün planlaşdırılmış tapşırıq və ya xatırlatma yoxdur. 📭")

    return "\n".join(lines).strip()


async def _build_digest(session, user_id: int) -> str:
    """Həftəlik icmal — son 7 günün qeyd/tapşırıq/xatırlatma xülasəsi."""
    now = now_utc()
    week_ago = now - timedelta(days=7)
    local = now_local()

    user = await get_user(session, user_id)
    name = (user.name.split()[0] if user and user.name else None)
    greet = f"📊 Həftəlik icmal, {name}!" if name else "📊 Həftəlik icmal!"
    lines = [greet, f"📅 {fmt_local(local, with_weekday=False)}", ""]

    n_notes = await count_notes_since(session, user_id, week_ago)
    lines.append(f"🗒 Bu həftə *{n_notes}* qeyd əlavə etdin.")

    cats = await category_counts_since(session, user_id, week_ago)
    if cats:
        lines.append("🏷 Əsas mövzular: " + ", ".join(f"{c} ({n})" for c, n in cats))

    open_tasks = await list_open_tasks(session, user_id, limit=100)
    if open_tasks:
        lines.append(f"📋 Açıq tapşırıqlar: *{len(open_tasks)}*")

    upcoming = await reminders_between(session, user_id, now, now + timedelta(days=7))
    if upcoming:
        lines.append(f"⏰ Növbəti 7 gündə *{len(upcoming)}* xatırlatma.")

    if not n_notes and not open_tasks and not upcoming:
        lines.append("Bu həftə sakit keçdi. 🌱")

    return "\n".join(lines).strip()


async def _maybe_send_briefing(context, session, uid, s, local, today) -> None:
    if not s.get("briefing_enabled", True):
        return
    if int(s.get("briefing_hour", BRIEFING_DEFAULT_HOUR)) != local.hour:
        return
    if s.get("briefing_last_sent") == today:
        return  # bu gün artıq göndərilib
    try:
        text = await _build_briefing(session, uid)
        await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
        await update_settings(session, uid, {"briefing_last_sent": today})
        log.info("briefing_sent", user_id=uid, hour=local.hour)
    except Exception as exc:  # noqa: BLE001
        log.warning("briefing_failed", user_id=uid, error=str(exc))


async def _maybe_send_digest(context, session, uid, s, local) -> None:
    if not s.get("digest_enabled", False):  # opt-in (default söndürülü)
        return
    weekday = int(s.get("digest_weekday", DIGEST_DEFAULT_WEEKDAY))
    hour = int(s.get("briefing_hour", BRIEFING_DEFAULT_HOUR))
    if local.weekday() != weekday or local.hour != hour:
        return
    iso = local.isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"
    if s.get("digest_last_sent") == week_key:
        return  # bu həftə artıq göndərilib
    try:
        text = await _build_digest(session, uid)
        await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
        await update_settings(session, uid, {"digest_last_sent": week_key})
        log.info("digest_sent", user_id=uid, week=week_key)
    except Exception as exc:  # noqa: BLE001
        log.warning("digest_failed", user_id=uid, error=str(exc))


async def briefing_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Saatbaşı: səhər brifinqi (gündəlik) + həftəlik digest yoxlaması.

    Per-user settings: briefing_enabled (default True), briefing_hour (default 8),
    digest_enabled (default False, opt-in), digest_weekday (default 0=B.e.).
    Təkrarın qarşısını almaq üçün son göndərilmə açarları saxlanılır.
    """
    recipients = settings.allowed_ids
    if not recipients:
        return
    local = now_local()
    today = local.date().isoformat()

    async with SessionLocal() as session:
        for uid in recipients:
            user = await get_user(session, uid)
            s = (user.settings if user else {}) or {}
            await _maybe_send_briefing(context, session, uid, s, local, today)
            await _maybe_send_digest(context, session, uid, s, local)
        await session.commit()


def _secs_to_next_hour() -> int:
    """İndidən növbəti tam saata (:00) qədər saniyə (tick-i saat başına düzləmək üçün)."""
    now = now_local()
    delta = 3600 - (now.minute * 60 + now.second)
    return delta if delta > 0 else 3600


def setup_jobs(application: Application) -> None:
    """JobQueue-a proaktiv işləri qeydiyyatdan keçirir (post_init-də çağırılır)."""
    jq = application.job_queue
    if jq is None:
        log.warning("job_queue_unavailable", hint="python-telegram-bot[job-queue] lazımdır")
        return

    jq.run_repeating(
        deliver_due_reminders,
        interval=REMINDER_INTERVAL_SEC,
        first=15,
        name="deliver_due_reminders",
    )
    jq.run_repeating(
        briefing_tick,
        interval=3600,
        first=_secs_to_next_hour(),
        name="briefing_tick",
    )
    log.info(
        "scheduler_ready",
        reminder_interval_sec=REMINDER_INTERVAL_SEC,
        briefing_default=f"{BRIEFING_DEFAULT_HOUR:02d}:00 {settings.timezone}",
        briefing_check="hourly",
    )
