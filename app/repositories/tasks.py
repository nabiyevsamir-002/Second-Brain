"""Tapşırıq (task) repository-si — yaratma, açıq siyahı, tamamlama."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskStatus


async def create_task(
    session: AsyncSession,
    user_id: int,
    title: str,
    *,
    due_at: datetime | None = None,
    source_note_id: int | None = None,
) -> Task:
    task = Task(
        user_id=user_id,
        title=title,
        due_at=due_at,
        source_note_id=source_note_id,
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
    """Tapşırığı 'done' et. Tapılmasa və ya başqa istifadəçininkisə None qaytarır."""
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id:
        return None
    task.status = TaskStatus.done
    await session.flush()
    return task
