import numpy as np
import pandas as pd
import pytest

from quant_engine.core import IST
from quant_engine.data import ExchangeCalendar, SyntheticMarket, resample_session
from support import MONDAY, BarFactory


def stamp(hhmm: str) -> pd.Timestamp:
    return pd.Timestamp(f"{MONDAY} {hhmm}", tz=IST)


def test_fifteen_minute_bars_aggregate_correctly(
    make_bars: BarFactory, calendar: ExchangeCalendar
) -> None:
    bars = make_bars(n=30)
    out = resample_session(bars, 15, calendar)
    assert list(out.index) == [stamp("09:15"), stamp("09:30")]
    first = out.iloc[0]
    assert first["open"] == bars["open"].iloc[0]
    assert first["high"] == bars["high"].iloc[:15].max()
    assert first["low"] == bars["low"].iloc[:15].min()
    assert first["close"] == bars["close"].iloc[14]
    assert first["volume"] == bars["volume"].iloc[:15].sum()
    assert list(out["available_at"]) == [stamp("09:30"), stamp("09:45")]
    assert out["complete"].all()


def test_bins_start_at_the_session_open_not_the_clock(
    make_bars: BarFactory, calendar: ExchangeCalendar
) -> None:
    bars = make_bars(n=20)
    ours = resample_session(bars, 10, calendar)
    clock_anchored = bars["close"].resample("10min").last()
    assert ours.index[0] == stamp("09:15")
    assert ours.iloc[0]["available_at"] == stamp("09:25")
    assert clock_anchored.index[0] == stamp("09:10")  # what plain pandas would have done


def test_missing_minutes_make_a_bar_incomplete(
    make_bars: BarFactory, calendar: ExchangeCalendar
) -> None:
    bars = make_bars(n=30).drop(index=stamp("09:20"))
    out = resample_session(bars, 15, calendar)
    assert out["bars"].tolist() == [14, 15]
    assert out["complete"].tolist() == [False, True]
    assert list(resample_session(bars, 15, calendar, drop_incomplete=True).index) == [
        stamp("09:30")
    ]


def test_blank_bars_are_skipped_and_an_all_blank_bin_is_kept(
    make_bars: BarFactory, calendar: ExchangeCalendar
) -> None:
    bars = make_bars(n=10)
    bars.iloc[0, :4] = np.nan
    bars.iloc[5:, :4] = np.nan
    out = resample_session(bars, 5, calendar)
    assert out.iloc[0]["open"] == bars["open"].iloc[1]  # first priced bar, not the blank
    assert out["bars"].tolist() == [4, 0]
    assert np.isnan(out.iloc[1]["close"])
    assert not out["complete"].any()


def test_a_short_last_bin_ends_at_the_close(calendar: ExchangeCalendar) -> None:
    day = SyntheticMarket(calendar, seed=3).minute_bars(MONDAY, MONDAY)
    out = resample_session(day, 10, calendar)
    close = calendar.session_close(MONDAY)
    assert len(out) == 38  # 375 minutes = 37 full bins and one of 5 minutes
    assert out.index[-1] == close - pd.Timedelta(minutes=5)
    assert out.iloc[-1]["available_at"] == close
    assert out.iloc[-1]["bars"] == 5
    assert out["complete"].all()


def test_bins_restart_each_day(calendar: ExchangeCalendar) -> None:
    bars = SyntheticMarket(calendar, seed=3).minute_bars(MONDAY, pd.Timestamp("2026-01-06").date())
    out = resample_session(bars, 60, calendar)
    assert len(out) == 2 * 7  # 6 full hours and a short last bin, twice
    assert out.index[7] == pd.Timestamp("2026-01-06 09:15", tz=IST)


def test_bars_outside_the_session_are_refused(
    make_bars: BarFactory, calendar: ExchangeCalendar
) -> None:
    with pytest.raises(ValueError, match="outside the session"):
        resample_session(make_bars(start="09:10", n=10), 5, calendar)
    with pytest.raises(ValueError, match="positive"):
        resample_session(make_bars(), 0, calendar)


def test_empty_input_gives_empty_output(make_bars: BarFactory, calendar: ExchangeCalendar) -> None:
    assert resample_session(make_bars().iloc[0:0], 15, calendar).empty
