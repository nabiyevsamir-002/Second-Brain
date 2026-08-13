"""Xatırlatma (reminder) repository-si — yaratma, çatdırılma növbəsi, siyahı.

remind_at tz-aware saxlanılır (Postgres daxildə UTC-yə çevirir). Müqayisələr
həmişə tz-aware datetime ilə aparılır (UTC), buna görə saat qurşağı təhlükəsizdir.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Reminder


async def create_reminder(
    session: AsyncSession, user_id: int, text: str, remind_at: datetime
) -> Reminder:
    reminder = Reminder(user_id=user_id, text=text, remind_at=remind_at)
    session.add(reminder)
    await session.flush()
    return reminder


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
