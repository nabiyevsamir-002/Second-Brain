"""Tapşırıq (task) repository-si — yaratma, açıq siyahı, tamamlama, təkrarlanma."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskStatus
from app.timeutils import now_utc

TASK_RECUR = {"daily", "weekly", "monthly"}


def _add_months(dt: datetime, n: int) -> datetime:
    """dt-yə n ay əlavə et (ayın günü daşarsa ayın son gününə sıxışdır)."""
    month = dt.month - 1 + n
    year = dt.year + month // 12
    month = month % 12 + 1
    # Növbəti ayın 1-dən 1 gün geri = cari ayın son günü (gün clamp üçün).
    if month == 12:
        last_day = 31
    else:
        last_day = (datetime(year, month + 1, 1) - timedelta(days=1)).day
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


def next_task_occurrence(due_at: datetime, recur: str, now: datetime) -> datetime:
    """Təkrarlanan tapşırığın `now`-dan sonrakı ilk deadline-ı."""
    nxt = due_at
    guard = 0
    while nxt <= now and guard < 500:
        if recur == "daily":
            nxt = nxt + timedelta(days=1)
        elif recur == "weekly":
            nxt = nxt + timedelta(weeks=1)
        else:  # monthly
            nxt = _add_months(nxt, 1)
        guard += 1
    return nxt


async def create_task(
    session: AsyncSession,
    user_id: int,
    title: str,
    *,
    due_at: datetime | None = None,
    source_note_id: int | None = None,
    recur: str | None = None,
) -> Task:
    task = Task(
        user_id=user_id,
        title=title,
        due_at=due_at,
        source_note_id=source_note_id,
        recur=recur if recur in TASK_RECUR else None,
    )
    session.add(task)
    await session.flush()
    return task


async def list_open_tasks(session: AsyncSession, user_id: int, limit: int = 50) -> list[Task]:
    """Açıq tapşırıqlar — vaxtı olanlar əvvəl (NULLS LAST), sonra yaranma sırası."""
    result = await session.execute(
        select(Task)
        .where(Task.user_id == user_id, Task.status == TaskStatus.open)
        .order_by(Task.due_at.asc().nulls_last(), Task.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_task(session: AsyncSession, task_id: int) -> Task | None:
    return await session.get(Task, task_id)


async def complete_task(session: AsyncSession, user_id: int, task_id: int) -> Task | None:
    """Tapşırığı 'done' et + completed_at yaz. Təkrarlanandırsa növbəti nüsxəni yarat.

    Tapılmasa və ya başqa istifadəçininkisə None qaytarır.
    """
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id:
        return None
    now = now_utc()
    task.status = TaskStatus.done
    task.completed_at = now
    # Təkrarlanan + deadline varsa növbəti açıq nüsxəni yarat.
    if task.recur in TASK_RECUR and task.due_at is not None:
        await create_task(
            session,
            user_id,
            task.title,
            due_at=next_task_occurrence(task.due_at, task.recur, now),
            recur=task.recur,
        )
    await session.flush()
    return task


async def count_tasks_completed_since(
    session: AsyncSession, user_id: int, since: datetime
) -> int:
    """`since`-dən bəri tamamlanan tapşırıqların sayı (activity report üçün)."""
    result = await session.execute(
        select(func.count())
        .select_from(Task)
        .where(
            Task.user_id == user_id,
            Task.status == TaskStatus.done,
            Task.completed_at.is_not(None),
            Task.completed_at >= since,
        )
    )
    return int(result.scalar() or 0)
