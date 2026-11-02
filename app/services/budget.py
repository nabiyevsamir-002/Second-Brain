"""Soft aylıq büdcə (xərc limiti) — usage_log əsasında, istifadəçi başına.

"Soft" = bot heç vaxt dayanmır. Bu ayın xərci limitin BUDGET_WARN_PCT %-inə çatanda
bir dəfə xəbərdarlıq gedir; limit keçiləndə yalnız bahalı əlavələr (Sonnet
eskalasiyası, səsli cavab) ayın sonunadək söndürülür — əsas funksiyalar (Haiku agent,
qeyd, axtarış, xatırlatma) işləməyə davam edir. MONTHLY_BUDGET_USD=0 → söndürülü.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.repositories.usage import usage_totals
from app.timeutils import now_local

# Bildiriş səviyyələri (hər biri ayda bir dəfə; "over" bildirilibsə "warn" artıq getmir).
_LEVELS = {"warn": 1, "over": 2}


@dataclass(frozen=True)
class BudgetStatus:
    state: str  # off | ok | warn | over
    spent: Decimal
    limit: Decimal

    @property
    def degraded(self) -> bool:
        """Limit keçilib → bahalı əlavələr söndürülür."""
        return self.state == "over"

    @property
    def pct(self) -> int:
        return int(self.spent * 100 / self.limit) if self.limit > 0 else 0


def budget_state(spent: Decimal, limit: Decimal, warn_pct: int) -> str:
    """Xərc/limit nisbətindən vəziyyət — saf funksiya."""
    if limit <= 0:
        return "off"
    if spent >= limit:
        return "over"
    if spent * 100 >= limit * warn_pct:
        return "warn"
    return "ok"


def status_for(spent: Decimal) -> BudgetStatus:
    """Bu ayın xərcindən cari konfiqurasiyaya görə büdcə vəziyyəti."""
    limit = Decimal(str(settings.monthly_budget_usd))
    return BudgetStatus(budget_state(spent, limit, settings.budget_warn_pct), spent, limit)


def month_start(now: datetime | None = None) -> datetime:
    """Cari local ayın başlanğıcı (tz-aware) — /stats ilə eyni sərhəd."""
    return (now or now_local()).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_key(now: datetime | None = None) -> str:
    return (now or now_local()).strftime("%Y-%m")


async def get_budget_status(session: AsyncSession, user_id: int) -> BudgetStatus:
    if settings.monthly_budget_usd <= 0:
        return status_for(Decimal("0"))  # söndürülü — DB sorğusu lazım deyil
    totals = await usage_totals(session, user_id, month_start())
    return status_for(sum((cost for _, cost in totals.values()), Decimal("0")))


def pending_notice(state: str, month: str, notified: str | None) -> str | None:
    """Bu ay hələ bildirilməmiş hədd ("warn"/"over") — yoxdursa None. Saf funksiya.

    notified = users.settings.budget_notified, format "YYYY-MM:warn" | "YYYY-MM:over".
    """
    level = _LEVELS.get(state)
    if level is None:
        return None
    prev_month, _, prev_state = (notified or "").partition(":")
    if prev_month == month and _LEVELS.get(prev_state, 0) >= level:
        return None
    return state


def notice_text(status: BudgetStatus) -> str:
    if status.state == "over":
        return (
            f"💰 Aylıq büdcə limiti keçildi: ~${status.spent:.2f} / ${status.limit:.2f}.\n"
            "Soft rejim: əsas funksiyalar işləyir, amma ayın sonunadək Sonnet eskalasiyası "
            "və səsli cavab söndürüldü. Ətraflı: /stats"
        )
    return (
        f"💰 Aylıq büdcənin {status.pct}%-i istifadə olunub: ~${status.spent:.2f} / "
        f"${status.limit:.2f}. Limit keçilsə Sonnet eskalasiyası və səsli cavab avtomatik "
        "söndürüləcək. Ətraflı: /stats"
    )
