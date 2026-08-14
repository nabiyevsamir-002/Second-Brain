"""Xatırlatma (reminder) repository-si — yaratma, çatdırılma növbəsi, siyahı.

remind_at tz-aware saxlanılır (Postgres daxildə UTC-yə çevirir). Müqayisələr
həmişə tz-aware datetime ilə aparılır (UTC), buna görə saat qurşağı təhlükəsizdir.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Reminder

# Dəstəklənən təkrarlanma addımları.
RECUR_STEPS = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}


async def create_reminder(
    session: AsyncSession,
    user_id: int,
    text: str,
    remind_at: datetime,
    recur: str | None = None,
) -> Reminder:
    recur = recur if recur in RECUR_STEPS else None
    reminder = Reminder(user_id=user_id, text=text, remind_at=remind_at, recur=recur)
    session.add(reminder)
    await session.flush()
    return reminder


def next_occurrence(remind_at: datetime, recur: str, now: datetime) -> datetime:
    """Təkrarlanan xatırlatmanın `now`-dan sonrakı ilk vaxtı (bot dayanıbsa da düz)."""
    step = RECUR_STEPS[recur]
    nxt = remind_at
    while nxt <= now:
        nxt = nxt + step
    return nxt


async def reschedule_or_mark_sent(
    session: AsyncSession, reminder: Reminder, now: datetime
) -> None:
    """Təkrarlanandırsa növbəti vaxta sürüşdür (sent=False qalır), yoxsa sent=True."""
    if reminder.recur in RECUR_STEPS:
        reminder.remind_at = next_occurrence(reminder.remind_at, reminder.recur, now)
        reminder.sent = False
    else:
        reminder.sent = True
    await session.flush()


async def due_reminders(session: AsyncSession, now: datetime, limit: int = 50) -> list[Reminder]:
    """Vaxtı çatmış, hələ göndərilməmiş xatırlatmalar (çatdırılma növbəsi)."""
    result = await session.execute(
        select(Reminder)
        .where(Reminder.sent.is_(False), Reminder.remind_at <= now)
        .order_by(Reminder.remind_at)
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_sent(session: AsyncSession, reminder_id: int) -> None:
    reminder = await session.get(Reminder, reminder_id)
    if reminder is not None:
        reminder.sent = True
        await session.flush()


async def list_pending(
    session: AsyncSession, user_id: int, limit: int = 20
) -> list[Reminder]:
    """İstifadəçinin gələcək (göndərilməmiş) xatırlatmaları — vaxta görə sıralı."""
    result = await session.execute(
        select(Reminder)
        .where(Reminder.user_id == user_id, Reminder.sent.is_(False))
        .order_by(Reminder.remind_at)
        .limit(limit)
    )
    return list(result.scalars().all())


async def reminders_between(
    session: AsyncSession, user_id: int, start: datetime, end: datetime
) -> list[Reminder]:
    """[start, end) aralığında olan göndərilməmiş xatırlatmalar (səhər brifinqi üçün)."""
    result = await session.execute(
        select(Reminder)
        .where(
            Reminder.user_id == user_id,
            Reminder.sent.is_(False),
            Reminder.remind_at >= start,
            Reminder.remind_at < end,
        )
        .order_by(Reminder.remind_at)
    )
    return list(result.scalars().all())
