"""Zaman köməkçiləri — Baku local ⇄ tz-aware datetime (Phase 4).

Agent (Claude) nisbi vaxtı system prompt-dakı cari Baku vaxtından hesablayır və
`YYYY-MM-DDTHH:MM` formatında local ISO qaytarır. Burada onu tz-aware edirik
(saxlama üçün), və göstərmə üçün yenidən local formata çeviririk.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings

# İstifadəçiyə göstərilən Azərbaycanca həftə günləri.
_WEEKDAYS_AZ = [
    "Bazar ertəsi",
    "Çərşənbə axşamı",
    "Çərşənbə",
    "Cümə axşamı",
    "Cümə",
    "Şənbə",
    "Bazar",
]


def now_local() -> datetime:
    """İndiki vaxt konfiqurasiya olunmuş saat qurşağında (tz-aware)."""
    return datetime.now(settings.tz)


def now_utc() -> datetime:
    """İndiki vaxt UTC-də (tz-aware) — çatdırılma müqayisələri üçün."""
    return datetime.now(timezone.utc)


def parse_local_iso(value: str) -> datetime:
    """Agent-in verdiyi ISO vaxtı tz-aware datetime-a çevir.

    tzinfo yoxdursa, dəyər local (Asia/Baku) sayılır. Xəta olarsa ValueError.
    """
    value = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)  # 3.11+ boşluq və offset-i qəbul edir
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=settings.tz)
    return dt


def fmt_local(dt: datetime, *, with_weekday: bool = True) -> str:
    """tz-aware datetime-ı local, oxunaqlı Azərbaycanca formata çevir."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(settings.tz)
    base = local.strftime("%Y-%m-%d %H:%M")
    if with_weekday:
        return f"{base} ({_WEEKDAYS_AZ[local.weekday()]})"
    return base


def now_local_prompt() -> str:
    """System prompt-a inject üçün cari vaxtın qısa təsviri."""
    return fmt_local(now_local())
