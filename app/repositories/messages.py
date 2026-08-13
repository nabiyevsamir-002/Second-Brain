"""Chat mesaj yaddaşı repository-si (messages) — agent konteksti üçün."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message


async def add_message(session: AsyncSession, user_id: int, role: str, content: str) -> None:
    session.add(Message(user_id=user_id, role=role, content=content))
    await session.flush()


async def get_recent_messages(
    session: AsyncSession, user_id: int, limit: int = 6
) -> list[dict[str, str]]:
    """Son mesajları xronoloji sırada (köhnədən yeniyə) qaytarır."""
    result = await session.execute(
        select(Message)
        .where(Message.user_id == user_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    msgs = list(result.scalars().all())
    msgs.reverse()
    return [{"role": m.role, "content": m.content} for m in msgs]
