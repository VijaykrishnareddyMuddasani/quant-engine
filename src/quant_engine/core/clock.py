"""Clocks: the one place the engine asks what time it is.

Live code takes a ``Clock`` instead of calling ``datetime.now()`` or ``time.sleep()`` directly.
The same order-handling code then runs against the wall clock in production and against a
simulated clock in tests, where a six-hour trading session replays in milliseconds and every
timing edge case (a candle published late, a retry that lands after the close) can be staged
exactly.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Protocol

IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")


class Clock(Protocol):
    """Anything that can tell the time and wait."""

    def now(self) -> dt.datetime:
        """The current time, always timezone-aware."""
        ...

    def sleep(self, seconds: float) -> None:
        """Block for ``seconds`` (or pretend to)."""
        ...


class SystemClock:
    """The wall clock, in a fixed timezone (IST by default)."""

    def __init__(self, tz: dt.tzinfo = IST) -> None:
        self._tz = tz

    def now(self) -> dt.datetime:
        return dt.datetime.now(self._tz)

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class SimulatedClock:
    """A clock that moves only when told to; ``sleep`` advances it instantly."""

    def __init__(self, start: dt.datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("SimulatedClock needs a timezone-aware start time")
        self._now = start

    def now(self) -> dt.datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError(f"cannot sleep a negative time ({seconds} s)")
        self._now += dt.timedelta(seconds=seconds)

    def advance_to(self, when: dt.datetime) -> None:
        """Jump to ``when``; time never moves backwards."""
        if when < self._now:
            raise ValueError(f"time cannot move backwards ({when} < {self._now})")
        self._now = when
