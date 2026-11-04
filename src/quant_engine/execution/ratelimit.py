"""Spacing calls to stay inside a broker's request limits."""

from __future__ import annotations

from quant_engine.core.clock import Clock


class RateLimiter:
    """Allows one call per ``min_interval_s``; ``wait`` sleeps (on the given clock) until it may."""

    def __init__(self, min_interval_s: float, clock: Clock) -> None:
        if min_interval_s < 0:
            raise ValueError("min_interval_s must be >= 0")
        self.min_interval_s = min_interval_s
        self.clock = clock
        self._last: float | None = None

    def wait(self) -> None:
        now = self.clock.now().timestamp()
        if self._last is not None:
            gap = self.min_interval_s - (now - self._last)
            if gap > 0:
                self.clock.sleep(gap)
                now = self.clock.now().timestamp()
        self._last = now
