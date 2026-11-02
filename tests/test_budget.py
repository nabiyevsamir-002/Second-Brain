from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.config import settings
from app.services.budget import (
    BudgetStatus,
    budget_state,
    month_key,
    month_start,
    notice_text,
    pending_notice,
    status_for,
)

D = Decimal


def test_budget_state_thresholds():
    assert budget_state(D("5"), D("0"), 80) == "off"
    assert budget_state(D("15.99"), D("20"), 80) == "ok"
    assert budget_state(D("16"), D("20"), 80) == "warn"  # dəqiq 80%
    assert budget_state(D("19.99"), D("20"), 80) == "warn"
    assert budget_state(D("20"), D("20"), 80) == "over"  # dəqiq 100%
    assert budget_state(D("35"), D("20"), 80) == "over"


def test_pending_notice_once_per_level_per_month():
    m = "2026-10"
    assert pending_notice("off", m, None) is None
    assert pending_notice("ok", m, None) is None
    assert pending_notice("warn", m, None) == "warn"
    assert pending_notice("warn", m, "2026-10:warn") is None
    assert pending_notice("over", m, "2026-10:warn") == "over"  # warn-dan sonra over yenə
    assert pending_notice("over", m, "2026-10:over") is None
    assert pending_notice("warn", m, "2026-10:over") is None  # over-dən sonra warn yox
    assert pending_notice("warn", m, "2026-09:over") == "warn"  # yeni ay — yenidən
    assert pending_notice("over", m, "zibil") == "over"


def test_status_for_reads_config(monkeypatch):
    monkeypatch.setattr(settings, "monthly_budget_usd", 20.0)
    monkeypatch.setattr(settings, "budget_warn_pct", 80)
    warn = status_for(D("17"))
    assert (warn.state, warn.pct, warn.degraded) == ("warn", 85, False)
    over = status_for(D("25"))
    assert over.degraded and over.pct == 125

    monkeypatch.setattr(settings, "monthly_budget_usd", 0.0)
    off = status_for(D("999"))
    assert off.state == "off" and not off.degraded


def test_month_helpers():
    baku = ZoneInfo("Asia/Baku")
    t = datetime(2026, 10, 31, 23, 59, tzinfo=baku)
    assert month_start(t) == datetime(2026, 10, 1, tzinfo=baku)
    assert month_key(t) == "2026-10"


def test_notice_text_mentions_amounts():
    warn = notice_text(BudgetStatus("warn", D("17"), D("20")))
    assert "85%" in warn and "$17.00 / $20.00" in warn
    over = notice_text(BudgetStatus("over", D("21.5"), D("20")))
    assert "keçildi" in over and "$21.50 / $20.00" in over
