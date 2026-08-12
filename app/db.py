"""Verilənlər bazası bağlantısı (async SQLAlchemy).

Phase 0-da yalnız bağlantı + sağlamlıq yoxlaması var (pgvector aktivdirmi?).
Data model (notes, users, ...) və Alembic migration-ları Phase 1-də gələcək.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def check_database() -> bool:
    """DB-yə qoşul və pgvector genişlənməsinin aktiv olduğunu yoxla.

    Returns:
        True — pgvector aktivdir; False — DB var amma pgvector yoxdur.
    Xəta olarsa exception qaldırır (çağıran tərəf tutur).
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        result = await conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        return result.scalar() is not None
