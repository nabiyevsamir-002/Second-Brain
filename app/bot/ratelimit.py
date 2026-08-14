"""Sadə per-user rate-limit (Phase 6) — runaway API xərcinə qarşı sığorta.

Sliding-window: son 60 san və son 60 dəq üzrə hadisə sayılır. Tək polling
instansı olduğu üçün yaddaşdaxili sayğac kifayətdir (paylaşılan state lazım deyil).
Limitlər config-dən (`RATE_LIMIT_PER_MIN`, `RATE_LIMIT_PER_HOUR`); 0 = limitsiz.

Yalnız BAHALI (API çağıran) əməliyyatlar sayılır — mətn/səs/sənəd/şəkil/link.
Ucuz DB əmrləri (/list, /stats, /tasks…) limitə düşmür.
"""

from __future__ import annotations

import time
from collections import deque

from app.config import settings
from app.logging_conf import get_logger

log = get_logger("ratelimit")

_HOUR = 3600
_MIN = 60


class SlidingWindowLimiter:
    def __init__(self, per_min: int, per_hour: int) -> None:
        self.per_min = per_min
        self.per_hour = per_hour
        self._events: dict[int, deque[float]] = {}

    def check(self, user_id: int) -> tuple[bool, int]:
        """(icazə verilir?, retry_after_san). İcazə verilirsə hadisə qeyd olunur."""
        now = time.monotonic()
        dq = self._events.setdefault(user_id, deque())

        # 1 saatdan köhnə hadisələri təmizlə (pəncərə sürüşür).
        while dq and now - dq[0] > _HOUR:
            dq.popleft()

        if self.per_hour and len(dq) >= self.per_hour:
            retry = int(_HOUR - (now - dq[0])) + 1
            log.warning("rate_limited", user_id=user_id, window="hour", count=len(dq))
            return False, max(1, retry)

        in_min = [t for t in dq if now - t <= _MIN]
        if self.per_min and len(in_min) >= self.per_min:
            retry = int(_MIN - (now - min(in_min))) + 1
            log.warning("rate_limited", user_id=user_id, window="min", count=len(in_min))
            return False, max(1, retry)

        dq.append(now)
        return True, 0


limiter = SlidingWindowLimiter(settings.rate_limit_per_min, settings.rate_limit_per_hour)
