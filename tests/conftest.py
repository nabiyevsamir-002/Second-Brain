"""Ortaq test qurğusu — testlər lokal .env-dən asılı olmasın."""

from __future__ import annotations

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def baku_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    # Vaxt testləri Asia/Baku (UTC+4) fərz edir; .env-də başqa dəyər olsa belə.
    monkeypatch.setattr(settings, "timezone", "Asia/Baku")
