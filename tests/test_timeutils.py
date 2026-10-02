from datetime import datetime, timedelta, timezone

import pytest

from app.bot.scheduler import _local_day_bounds
from app.timeutils import fmt_local, parse_local_iso

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
