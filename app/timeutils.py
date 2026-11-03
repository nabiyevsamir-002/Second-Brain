"""Zaman köməkçiləri — Baku local ⇄ tz-aware datetime (Phase 4).

Agent (Claude) nisbi vaxtı system prompt-dakı cari Baku vaxtından hesablayır və
`YYYY-MM-DDTHH:MM` formatında local ISO qaytarır. Burada onu tz-aware edirik
(saxlama üçün), və göstərmə üçün yenidən local formata çeviririk.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


# Gecə yarısından bu saata qədər istifadəçinin günü hələ bitməyib (yatmayıb).
NIGHT_END_HOUR = 5


def time_context_prompt(now: datetime | None = None) -> str:
    """System prompt üçün cari vaxt bloku: CARİ VAXT + nisbi vaxt qaydası.

    Gecə (00:00–05:00) istifadəçinin "sabah"ı yatıb duranda gələn gündür, yəni
    təqvimdə BU GÜN. Agent onu təqvimlə hesablayıb bir gün sonraya qoymasın deyə
    tarixləri hazır yazırıq.
    """
    local = (now or now_local()).astimezone(settings.tz)
    text = (
        f"CARİ VAXT (Asia/Baku): {fmt_local(local)}. Nisbi vaxtları ('sabah', "
        "'2 saatdan sonra', 'cümə axşamı 9-da') HƏMİŞƏ bu vaxta əsasən hesabla."
    )
    if local.hour < NIGHT_END_HOUR:
        today, tomorrow = local.date(), local.date() + timedelta(days=1)
        text += (
            " GECƏ QAYDASI: indi gecədir, istifadəçi hələ yatmayıb. Onun 'sabah' "
            "('sabah səhər', 'sabah 9-da') dediyi gün yatıb duranda gələn gündür: "
            f"BU GÜN, {today.isoformat()} ({_WEEKDAYS_AZ[today.weekday()]}), "
            f"{tomorrow.isoformat()} YOX. 'Birisigün' isə {tomorrow.isoformat()} "
            f"({_WEEKDAYS_AZ[tomorrow.weekday()]}) deməkdir."
        )
    return text
