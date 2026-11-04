import datetime as dt

import numpy as np
import pandas as pd
import pytest

from quant_engine.data import (
    ExchangeCalendar,
    SyntheticMarket,
    blank,
    blank_runs,
    find_carried_bars,
    find_missing_minutes,
    find_stale_runs,
    find_unlisted_closures,
)
from support import MONDAY, BarFactory


def freeze(bars: pd.DataFrame, rows: slice, price: float) -> pd.DataFrame:
    """Make the given rows flat bars at one price, the way a stalled feed prints them."""
    out = bars.copy()
    out.iloc[rows, :4] = price
    return out


def test_a_frozen_stretch_is_one_stale_run(make_bars: BarFactory) -> None:
    bars = freeze(make_bars(n=12), slice(3, 9), 105.0)
    runs = find_stale_runs(bars, min_bars=5)
    assert len(runs) == 1
    assert (runs[0].start, runs[0].end) == (bars.index[3], bars.index[8])
    assert runs[0].bars == 6
    assert runs[0].price == 105.0
    assert find_stale_runs(bars, min_bars=7) == []


def test_flat_bars_at_changing_prices_are_not_stale(make_bars: BarFactory) -> None:
    bars = make_bars(n=8)
    bars.iloc[:, :4] = np.repeat(np.arange(100.0, 108.0)[:, None], 4, axis=1)
    assert find_stale_runs(bars, min_bars=3) == []


def test_stale_runs_do_not_span_the_overnight_break(make_bars: BarFactory) -> None:
    friday = make_bars(day=dt.date(2026, 1, 9), start="15:27", n=3)
    monday = make_bars(day=dt.date(2026, 1, 12), n=3)
    bars = freeze(pd.concat([friday, monday]), slice(0, 6), 100.0)
    assert find_stale_runs(bars, min_bars=4) == []
    assert len(find_stale_runs(bars, min_bars=3)) == 2


def test_carried_bars_are_flat_and_untraded(make_bars: BarFactory) -> None:
    bars = freeze(make_bars(n=4), slice(1, 3), 101.0)
    bars.iloc[1, bars.columns.get_loc("volume")] = 0  # flat, nothing traded: carried
    # row 2 is flat but traded: a real, quiet print
    assert find_carried_bars(bars).tolist() == [False, True, False, False]
    with pytest.raises(ValueError, match="volume"):
        find_carried_bars(bars.drop(columns="volume"))


def test_missing_minutes_are_found(calendar: ExchangeCalendar) -> None:
    bars = SyntheticMarket(calendar, seed=1).minute_bars(MONDAY, MONDAY)
    gone = bars.index[[10, 200]]
    assert find_missing_minutes(bars.drop(index=gone), calendar).equals(gone)
    assert find_missing_minutes(bars, calendar).empty


def test_unlisted_closures_find_a_missing_weekday(calendar: ExchangeCalendar) -> None:
    bars = SyntheticMarket(calendar, seed=1).minute_bars(dt.date(2026, 1, 5), dt.date(2026, 1, 7))
    tuesday = dt.date(2026, 1, 6)
    without_tuesday = bars[bars.index.date != tuesday]
    assert find_unlisted_closures(without_tuesday, calendar) == [tuesday]
    assert find_unlisted_closures(bars, calendar) == []


def test_blank_sets_prices_to_nan_and_leaves_the_input_alone(make_bars: BarFactory) -> None:
    bars = make_bars(n=4)
    repaired = blank(bars, np.array([False, True, False, False]))
    assert repaired.iloc[1].isna().all()
    assert repaired.iloc[[0, 2, 3]].notna().all().all()
    assert bars.notna().all().all()
    with pytest.raises(ValueError, match="mask"):
        blank(bars, np.array([True]))


def test_blank_runs_removes_exactly_the_frozen_bars(make_bars: BarFactory) -> None:
    bars = freeze(make_bars(n=12), slice(3, 9), 105.0)
    repaired = blank_runs(bars, find_stale_runs(bars))
    assert repaired["close"].isna().tolist() == [False] * 3 + [True] * 6 + [False] * 3
