"""Detectors for data hazards found in real vendor bar data, and the one repair the engine makes.

Each detector answers a narrow question and returns something a person can look at. None of them
changes data. The repair, ``blank``, sets bad bars to NaN rather than guessing a better price, so
anything computed from a repaired bar fails visibly instead of trading on an invented number.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_engine.data.calendar import ExchangeCalendar
from quant_engine.data.schema import OHLC, datetime_index


@dataclass(frozen=True)
class StaleRun:
    """Consecutive flat bars at one unchanged price."""

    start: pd.Timestamp
    end: pd.Timestamp
    bars: int
    price: float


def _flat(df: pd.DataFrame) -> pd.Series[bool]:
    return (df["open"] == df["high"]) & (df["high"] == df["low"]) & (df["low"] == df["close"])


def find_stale_runs(df: pd.DataFrame, min_bars: int = 5) -> list[StaleRun]:
    """Runs of at least ``min_bars`` consecutive flat bars at one price, within one day.

    A live index never prints the same flat minute five times running. Such a run is a feed that
    stopped updating. The case that prompted this detector: since the 2026 introduction of a
    closing auction for index constituents, vendor minute series for the indices freeze for a
    stretch before the close and then jump to the auction print. Logic that evaluates a stop or a
    signal on those bars reacts to a market that did not exist.
    """
    if min_bars < 2:
        raise ValueError("min_bars must be at least 2")
    flat = _flat(df)
    day = pd.Series(datetime_index(df).normalize(), index=df.index)
    continues = (
        flat
        & flat.shift(1, fill_value=False)
        & (df["close"] == df["close"].shift(1))
        & (day == day.shift(1))
    )
    run_id = (~continues).cumsum()
    runs = []
    for _, run in df[flat].groupby(run_id[flat]):
        if len(run) >= min_bars:
            runs.append(
                StaleRun(run.index[0], run.index[-1], len(run), float(run["close"].iloc[0]))
            )
    return runs


def find_carried_bars(df: pd.DataFrame) -> pd.Series[bool]:
    """Flat bars with zero volume: minutes in which nothing traded.

    Option data vendors fill untraded minutes with the last traded price, sometimes minutes or hours
    old and occasionally taken from a neighbouring strike. A backtest that fills at such a price is
    trading at a price nobody could have traded. Deep in-the-money strikes, which trade rarely, are
    the worst affected. A real print needs volume above zero.
    """
    if "volume" not in df.columns:
        raise ValueError("find_carried_bars needs a volume column")
    return _flat(df) & (df["volume"] == 0)


def find_missing_minutes(df: pd.DataFrame, calendar: ExchangeCalendar) -> pd.DatetimeIndex:
    """Session minutes absent from a one-minute series, over the trading days it spans."""
    if df.empty:
        return calendar.empty_index()
    local = datetime_index(df).tz_convert(calendar.tz)
    expected = calendar.minute_index(local[0].date(), local[-1].date())
    return expected.difference(local.as_unit("ns"))


def find_unlisted_closures(df: pd.DataFrame, calendar: ExchangeCalendar) -> list[dt.date]:
    """Days the calendar says should trade but the data has no bars for.

    Usually a holiday declared after the list was written (an election day), sometimes a day the
    download lost. Either way the calendar and the data disagree, and someone should decide which
    is wrong before a backtest silently treats the day as flat.
    """
    if df.empty:
        return []
    local = datetime_index(df).tz_convert(calendar.tz)
    present = set(local.normalize().date)
    return [d for d in calendar.trading_days(local[0].date(), local[-1].date()) if d not in present]


def blank(df: pd.DataFrame, mask: pd.Series[bool] | np.ndarray) -> pd.DataFrame:
    """A copy of ``df`` with prices (and volume) set to NaN where ``mask`` is True."""
    flags = np.asarray(mask, dtype=bool)
    if len(flags) != len(df):
        raise ValueError(f"mask has {len(flags)} entries for {len(df)} rows")
    out = df.copy()
    columns = [c for c in (*OHLC, "volume") if c in out.columns]
    out[columns] = out[columns].astype(float)
    out.loc[flags, columns] = np.nan
    return out


def blank_runs(df: pd.DataFrame, runs: list[StaleRun]) -> pd.DataFrame:
    """Blank every bar inside the given stale runs."""
    mask = np.zeros(len(df), dtype=bool)
    for run in runs:
        mask |= np.asarray((df.index >= run.start) & (df.index <= run.end))
    return blank(df, mask)
