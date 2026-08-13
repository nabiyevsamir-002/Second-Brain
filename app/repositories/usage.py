"""İstifadə/xərc logu repository-si (usage_log).

Phase 1-də sadə: kind + tokens qeyd olunur. Dəqiq cost hesablaması
(model qiymətləri) Phase 5 (cost dashboard) mərhələsində əlavə olunacaq.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UsageLog


async def log_usage(
    session: AsyncSession,
    user_id: int | None,
    kind: str,
    tokens: int = 0,
    cost: Decimal | float = 0,
) -> None:
    session.add(
        UsageLog(
            user_id=user_id,
            kind=kind,
            tokens=tokens,
            cost=Decimal(str(cost)),
        )
    )
    await session.flush()
