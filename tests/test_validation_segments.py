import datetime as dt
import itertools

import pytest

from quant_engine.data import ExchangeCalendar, SyntheticMarket
from quant_engine.validation import (
    GridSearch,
    Segment,
    chronological_segments,
    draw_segments,
    run_walk_forward,
    trading_days_of,
    walk_forward_folds,
)

CALENDAR = ExchangeCalendar.nse()
DAYS = CALENDAR.trading_days(dt.date(2026, 1, 1), dt.date(2026, 6, 30))


def test_segments_are_contiguous_balanced_and_cover_every_day() -> None:
    segments = chronological_segments(DAYS, 5)
    sizes = [sum(s.contains(d) for d in DAYS) for s in segments]
    assert max(sizes) - min(sizes) <= 1
    assert sum(sizes) == len(DAYS)
    assert [s.name for s in segments] == ["P1", "P2", "P3", "P4", "P5"]
    for before, after in itertools.pairwise(segments):
        assert CALENDAR.next_trading_day(before.end) == after.start


def test_segment_selects_its_bars() -> None:
    bars = SyntheticMarket(CALENDAR, seed=1).minute_bars(DAYS[0], DAYS[9])
    segment = Segment("x", DAYS[2], DAYS[4])
    assert trading_days_of(segment.select(bars)) == DAYS[2:5]


def test_draws_are_reproducible_and_in_time_order() -> None:
    segments = chronological_segments(DAYS, 5)
    first = draw_segments(segments, 2, seed=7)
    assert first == draw_segments(segments, 2, seed=7)
    assert first[0].start < first[1].start
    with pytest.raises(ValueError, match="cannot draw"):
        draw_segments(segments, 6, seed=1)


def test_bad_segment_requests_are_refused() -> None:
    with pytest.raises(ValueError, match="cannot cut"):
        chronological_segments(DAYS[:3], 5)
    with pytest.raises(ValueError, match="ends before"):
        Segment("bad", DAYS[5], DAYS[1])


def test_rolling_and_anchored_folds() -> None:
    days = DAYS[:100]
    rolling = walk_forward_folds(days, train_days=40, test_days=20)
    assert len(rolling) == 3
    assert rolling[1].train.start == days[20]
    assert rolling[1].test.start == days[60]
    anchored = walk_forward_folds(days, train_days=40, test_days=20, anchored=True)
    assert all(f.train.start == days[0] for f in anchored)
    with pytest.raises(ValueError, match="too few"):
        walk_forward_folds(days[:30], train_days=40, test_days=20)


def test_grid_search_keeps_the_best_and_counts_every_trial() -> None:
    search = GridSearch([1, 2, 3], lambda bars, p: {1: 0.5, 2: float("nan"), 3: 0.9}[p])
    assert search(None) == 3  # type: ignore[arg-type]
    assert search.trials == 3


def test_walk_forward_only_scores_the_test_windows() -> None:
    from quant_engine.backtest import Backtester
    from quant_engine.data import resample_session
    from quant_engine.strategy.examples import MovingAverageCrossover

    minutes = SyntheticMarket(CALENDAR, seed=5).minute_bars(DAYS[0], DAYS[59])
    bars = resample_session(minutes, 30, CALENDAR)
    folds = walk_forward_folds(trading_days_of(bars), train_days=30, test_days=10)
    report = run_walk_forward(
        bars,
        folds,
        GridSearch([(3, 6), (4, 10)], lambda b, p: float(len(b)) + p[0]),
        lambda b, p: Backtester(MovingAverageCrossover(*p)).run(b),
    )
    assert list(report.summary()["fold"]) == [1, 2, 3]
    trades = report.out_of_sample_trades()
    first_test_day = folds[0].test.start
    assert (trades["entry_time"].dt.date >= first_test_day).all()
