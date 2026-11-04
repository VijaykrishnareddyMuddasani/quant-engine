import datetime as dt

import pytest

from quant_engine.core import IST, SimulatedClock, SystemClock

START = dt.datetime(2026, 1, 5, 9, 15, tzinfo=IST)


def test_simulated_sleep_moves_time_instantly() -> None:
    clock = SimulatedClock(START)
    clock.sleep(90.5)
    assert clock.now() == START + dt.timedelta(seconds=90.5)


def test_simulated_clock_never_moves_backwards() -> None:
    clock = SimulatedClock(START)
    with pytest.raises(ValueError, match="backwards"):
        clock.advance_to(START - dt.timedelta(seconds=1))
    with pytest.raises(ValueError, match="negative"):
        clock.sleep(-1)


def test_simulated_clock_needs_an_aware_start() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SimulatedClock(dt.datetime(2026, 1, 5, 9, 15))


def test_system_clock_is_aware_and_in_ist() -> None:
    now = SystemClock().now()
    assert now.utcoffset() == dt.timedelta(hours=5, minutes=30)
