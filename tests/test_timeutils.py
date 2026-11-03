from datetime import datetime, timedelta, timezone

import pytest

from app.bot.scheduler import _local_day_bounds
from app.timeutils import fmt_local, parse_local_iso, time_context_prompt

BAKU = timezone(timedelta(hours=4))


def test_parse_local_iso_treats_naive_time_as_baku():
    dt = parse_local_iso("2026-10-05T09:30")
    assert dt.utcoffset() == timedelta(hours=4)
    assert dt.astimezone(timezone.utc) == datetime(2026, 10, 5, 5, 30, tzinfo=timezone.utc)


def test_parse_local_iso_keeps_explicit_offsets():
    assert parse_local_iso("2026-10-05T09:30Z").utcoffset() == timedelta(0)
    assert parse_local_iso(" 2026-10-05T09:30+03:00 ").utcoffset() == timedelta(hours=3)


def test_parse_local_iso_rejects_garbage():
    with pytest.raises(ValueError):
        parse_local_iso("sabah səhər")


def test_fmt_local_converts_to_baku_with_azerbaijani_weekday():
    utc = datetime(2026, 10, 5, 5, 30, tzinfo=timezone.utc)  # Bazar ertəsi
    assert fmt_local(utc) == "2026-10-05 09:30 (Bazar ertəsi)"
    assert fmt_local(utc, with_weekday=False) == "2026-10-05 09:30"


def test_fmt_local_treats_naive_datetime_as_utc():
    assert fmt_local(datetime(2026, 10, 4, 20, 0), with_weekday=False) == "2026-10-05 00:00"


def test_local_day_bounds_cover_the_whole_day():
    start, end = _local_day_bounds(datetime(2026, 10, 5, 15, 42, 7, tzinfo=BAKU))
    assert start == datetime(2026, 10, 5, tzinfo=BAKU)
    assert end - start == timedelta(days=1)


def test_time_context_prompt_at_night_maps_sabah_to_today():
    # 01:15-də yazılan "sabah səhər ... xatırlat" əvvəl bir gün sonraya düşürdü.
    prompt = time_context_prompt(datetime(2026, 11, 2, 21, 15, tzinfo=timezone.utc))
    assert "CARİ VAXT (Asia/Baku): 2026-11-03 01:15 (Çərşənbə axşamı)" in prompt
    assert "BU GÜN, 2026-11-03 (Çərşənbə axşamı), 2026-11-04 YOX" in prompt
    assert "'Birisigün' isə 2026-11-04 (Çərşənbə)" in prompt


@pytest.mark.parametrize(("hour", "night"), [(0, True), (4, True), (5, False), (23, False)])
def test_time_context_prompt_adds_night_rule_only_before_5(hour, night):
    prompt = time_context_prompt(datetime(2026, 11, 3, hour, 59, tzinfo=BAKU))
    assert prompt.startswith("CARİ VAXT (Asia/Baku): 2026-11-03")
    assert ("GECƏ QAYDASI" in prompt) is night
