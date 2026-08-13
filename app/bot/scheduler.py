"""Proaktiv scheduler (Phase 4) — PTB JobQueue əsasında.

İki iş:
  • deliver_due_reminders — hər 60 san: vaxtı çatmış xatırlatmaları çatdırır.
  • morning_briefing — hər gün səhər: günün tapşırıq/xatırlatma/qeyd icmalı.

Gecə pg_dump backup host cron ilə işləyir (scripts/backup.sh) — burada deyil.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from telegram.ext import Application, ContextTypes

from app.config import settings
from app.db import SessionLocal
from app.logging_conf import get_logger
from app.models import TaskStatus
from app.repositories.notes import count_notes_since
from app.repositories.reminders import due_reminders, mark_sent, reminders_between
from app.repositories.tasks import list_open_tasks
from app.repositories.users import get_user, update_settings
from app.timeutils import fmt_local, now_local, now_utc

log = get_logger("scheduler")

REMINDER_INTERVAL_SEC = 60
BRIEFING_DEFAULT_HOUR = 8  # local (Asia/Baku) — istifadəçi /settings ilə dəyişə bilər


async def deliver_due_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vaxtı çatmış, göndərilməmiş xatırlatmaları Telegram-a çatdırır."""
    now = now_utc()
    async with SessionLocal() as session:
        due = await due_reminders(session, now)
        for r in due:
            try:
                await context.bot.send_message(
                    chat_id=r.user_id, text=f"⏰ Xatırlatma: {r.text}"
                )
                await mark_sent(session, r.id)
                log.info("reminder_delivered", reminder_id=r.id, user_id=r.user_id)
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


async def briefing_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Saatbaşı: hər istifadəçinin brifinq saatı gəlibsə (və aktivdirsə) göndərir.

    Per-user settings: briefing_enabled (default True), briefing_hour (default 8).
    Günə bir dəfə göndərilməsi üçün settings-də son göndərilmə tarixi saxlanılır.
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
            if not s.get("briefing_enabled", True):
                continue
            if int(s.get("briefing_hour", BRIEFING_DEFAULT_HOUR)) != local.hour:
                continue
            if s.get("briefing_last_sent") == today:
                continue  # bu gün artıq göndərilib
            try:
                text = await _build_briefing(session, uid)
                await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
                await update_settings(session, uid, {"briefing_last_sent": today})
                log.info("briefing_sent", user_id=uid, hour=local.hour)
            except Exception as exc:  # noqa: BLE001
                log.warning("briefing_failed", user_id=uid, error=str(exc))
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
