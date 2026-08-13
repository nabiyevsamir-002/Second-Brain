"""İstifadəçi repository-si."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_or_create_user(
    session: AsyncSession, telegram_id: int, name: str | None = None
) -> User:
    user = await session.get(User, telegram_id)
    if user is None:
        user = User(telegram_id=telegram_id, name=name)
        session.add(user)
        await session.flush()
    elif name and user.name != name:
        user.name = name
    return user


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.get(User, telegram_id)


async def update_settings(
    session: AsyncSession, telegram_id: int, changes: dict
) -> dict:
    """settings JSONB-ni birləşdir və yenilə (yeni dict = dəyişiklik detect olunur)."""
    user = await session.get(User, telegram_id)
    if user is None:
        user = User(telegram_id=telegram_id, settings=dict(changes))
        session.add(user)
        await session.flush()
        return user.settings
    merged = {**(user.settings or {}), **changes}
    user.settings = merged  # yeni obyekt təyin et — SQLAlchemy dəyişikliyi görsün
    await session.flush()
    return merged


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())
