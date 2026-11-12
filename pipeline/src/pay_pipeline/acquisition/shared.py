"""Politeness shared between threads.

:class:`PoliteFetcher` keeps its per-host clock inside one instance, so it is not safe to share
between threads. Discovery crawls many district websites at once (one fetcher per worker
thread); :class:`SharedThrottle` keeps one clock per host for all of them, so two threads never
hit the same host (a shared CDN, say) closer together than the policy allows.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from collections.abc import Callable
from typing import Any

from pay_pipeline.acquisition.http import BudgetExceededError, PoliteFetcher
from pay_pipeline.acquisition.policy import CrawlPolicy


class SharedThrottle:
    def __init__(
        self,
        policy: CrawlPolicy,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._next_slot: dict[str, float] = {}
        self._count: Counter[str] = Counter()

    def wait(self, host: str) -> None:
        """Reserve the next allowed slot for ``host`` and sleep until it."""
        with self._lock:
            if self._count[host] >= self.policy.max_requests_per_host_per_run:
                raise BudgetExceededError(f"Đã đạt giới hạn yêu cầu cho {host} trong lần chạy này")
            now = self._clock()
            slot = max(now, self._next_slot.get(host, now))
            self._next_slot[host] = slot + self.policy.min_delay_seconds
            self._count[host] += 1
        if slot > now:
            self._sleep(slot - now)


class SharedPoliteFetcher(PoliteFetcher):
    """A :class:`PoliteFetcher` whose per-host delay and budget come from a shared throttle."""

    def __init__(self, throttle: SharedThrottle, **kwargs: Any) -> None:
        super().__init__(throttle.policy, **kwargs)
        self._shared = throttle

    def _throttle(self, host: str) -> None:
        self._shared.wait(host)
