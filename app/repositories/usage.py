"""İstifadə/xərc logu repository-si (usage_log).

Phase 1-də sadə: kind + tokens qeyd olunur. Dəqiq cost hesablaması
(model qiymətləri) Phase 5 (cost dashboard) mərhələsində əlavə olunacaq.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UsageLog
from app.pricing import llm_cost


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


async def log_llm_usage(
    session: AsyncSession, user_id: int | None, model: str, usage: Any
) -> None:
    """Claude cavabının `usage` obyektindən token+cost loglar (kind='llm').

    Prompt caching açıqdırsa cache yazma/oxuma tokenləri də nəzərə alınır ki,
    /stats-dakı xərc dəqiq qalsın.
    """
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    cw = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cr = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    await log_usage(
        session,
        user_id,
        "llm",
        tokens=inp + out + cw + cr,
        cost=llm_cost(model, inp, out, cw, cr),
    )


async def usage_totals(
    session: AsyncSession, user_id: int, since: datetime
) -> dict[str, tuple[int, Decimal]]:
    """`since`-dən bəri kind üzrə (tokens, cost) cəmi."""
    result = await session.execute(
        select(
            UsageLog.kind,
            func.coalesce(func.sum(UsageLog.tokens), 0),
            func.coalesce(func.sum(UsageLog.cost), 0),
        )
        .where(UsageLog.user_id == user_id, UsageLog.created_at >= since)
        .group_by(UsageLog.kind)
    )
    return {row[0]: (int(row[1]), Decimal(row[2])) for row in result.all()}
