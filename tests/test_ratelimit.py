import pytest

from app.bot import ratelimit
from app.bot.ratelimit import SlidingWindowLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(ratelimit.time, "monotonic", fake)
    return fake


def test_per_minute_limit_blocks_then_recovers(clock):
    limiter = SlidingWindowLimiter(per_min=2, per_hour=0)
    assert limiter.check(1) == (True, 0)
    assert limiter.check(1) == (True, 0)

    clock.now += 10
    allowed, retry = limiter.check(1)
    assert not allowed
    assert retry == 51  # 60 - 10 + 1

    clock.now += 51
    assert limiter.check(1) == (True, 0)


def test_per_hour_limit(clock):
    limiter = SlidingWindowLimiter(per_min=0, per_hour=3)
    for _ in range(3):
        assert limiter.check(1)[0]
        clock.now += 120

    allowed, retry = limiter.check(1)
    assert not allowed
    assert retry == 3600 - 360 + 1

    clock.now += retry
    assert limiter.check(1)[0]


def test_users_are_limited_separately(clock):
    limiter = SlidingWindowLimiter(per_min=1, per_hour=0)
    assert limiter.check(1)[0]
    assert not limiter.check(1)[0]
    assert limiter.check(2)[0]


def test_zero_means_unlimited(clock):
    limiter = SlidingWindowLimiter(per_min=0, per_hour=0)
    assert all(limiter.check(1)[0] for _ in range(500))


def test_blocked_attempts_are_not_counted(clock):
    limiter = SlidingWindowLimiter(per_min=1, per_hour=0)
    assert limiter.check(1)[0]
    for _ in range(5):
        assert not limiter.check(1)[0]
    clock.now += 61
    assert limiter.check(1)[0]
