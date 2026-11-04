import datetime as dt

import numpy as np
import pandas as pd
import pytest

from quant_engine.data import ExchangeCalendar, SyntheticConfig, SyntheticMarket, validate_ohlcv

START, END = dt.date(2026, 1, 1), dt.date(2026, 12, 31)


@pytest.fixture(scope="module")
def year() -> pd.DataFrame:
    return SyntheticMarket(ExchangeCalendar.nse(), seed=11).minute_bars(START, END)


def daily_closes(bars: pd.DataFrame) -> pd.Series:
    return bars["close"].groupby(bars.index.date).last()


def test_bars_are_valid_and_on_the_calendar(year: pd.DataFrame) -> None:
    calendar = ExchangeCalendar.nse()
    validate_ohlcv(year, calendar, require_volume=True, allow_blank=False).raise_if_failed()
    assert year.index.equals(calendar.minute_index(START, END))


def test_prices_sit_on_the_tick_grid(year: pd.DataFrame) -> None:
    ticks = year[["open", "high", "low", "close"]].to_numpy() / 0.05
    assert np.allclose(ticks, np.round(ticks), atol=1e-6)


def test_same_seed_same_bars_other_seed_other_bars() -> None:
    calendar = ExchangeCalendar.nse()
    week = (dt.date(2026, 2, 2), dt.date(2026, 2, 6))
    a = SyntheticMarket(calendar, seed=5).minute_bars(*week)
    b = SyntheticMarket(calendar, seed=5).minute_bars(*week)
    c = SyntheticMarket(calendar, seed=6).minute_bars(*week)
    pd.testing.assert_frame_equal(a, b)
    assert not a["close"].equals(c["close"])


def test_days_open_with_a_gap(year: pd.DataFrame) -> None:
    first_open = year["open"].groupby(year.index.date).first()
    previous_close = daily_closes(year).shift(1)
    gapped = (first_open != previous_close).iloc[1:]
    assert gapped.mean() > 0.95


def test_intraday_volatility_is_u_shaped(year: pd.DataFrame) -> None:
    moves = np.log(year["close"] / year["open"]).abs()
    minute = (year.index.hour - 9) * 60 + year.index.minute - 15
    opening = moves[minute < 15].mean()
    midday = moves[(minute >= 180) & (minute < 195)].mean()
    assert opening > 1.4 * midday


def test_realised_volatility_is_near_the_target(year: pd.DataFrame) -> None:
    daily = np.log(daily_closes(year)).diff().dropna()
    realised = daily.std() * np.sqrt(250)
    assert 0.7 * 0.14 < realised < 1.4 * 0.14


def test_garch_produces_volatility_clustering() -> None:
    calendar = ExchangeCalendar.nse()
    span = (dt.date(2026, 1, 1), dt.date(2026, 12, 31))

    def abs_return_autocorrelation(config: SyntheticConfig) -> float:
        bars = SyntheticMarket(calendar, config, seed=2).minute_bars(*span)
        size = np.log(daily_closes(bars)).diff().dropna().abs()
        return float(size.autocorr(lag=1))

    clustered = abs_return_autocorrelation(SyntheticConfig(garch_alpha=0.15, garch_beta=0.83))
    constant = abs_return_autocorrelation(SyntheticConfig(garch_alpha=0.0, garch_beta=0.0))
    assert clustered > constant + 0.1


def test_a_closed_range_gives_an_empty_frame() -> None:
    weekend = SyntheticMarket(ExchangeCalendar.nse(), seed=1).minute_bars(
        dt.date(2026, 1, 3), dt.date(2026, 1, 4)
    )
    assert weekend.empty
    assert list(weekend.columns) == ["open", "high", "low", "close", "volume"]


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ({"garch_alpha": 0.2, "garch_beta": 0.8}, "stationary"),
        ({"overnight_share": 1.0}, "overnight_share"),
        ({"tail_dof": 2.0}, "tail_dof"),
        ({"annual_vol": 0.0}, "positive"),
    ],
)
def test_invalid_configs_are_rejected(bad: dict[str, float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        SyntheticConfig(**bad)
