"""Performance statistics. Each takes plain Series or arrays, so the validation layer can reuse them
on resampled or bootstrapped trade sequences."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
import pandas as pd

TRADING_DAYS_PER_YEAR = 250

# Anything np.asarray turns into a float vector: a list, a Series or an array.
Numbers = Sequence[float] | pd.Series | npt.NDArray[np.floating]


def t_statistic(values: Numbers) -> float:
    """Mean over its standard error: how many standard errors the average is from zero."""
    x = np.asarray(values, dtype=float)
    if len(x) < 2:
        return math.nan
    spread = x.std(ddof=1)
    return math.nan if spread == 0 else float(x.mean() / (spread / math.sqrt(len(x))))


def sharpe_ratio(returns: Numbers, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Annualised mean over standard deviation of periodic returns (no risk-free rate)."""
    x = np.asarray(returns, dtype=float)
    if len(x) < 2:
        return math.nan
    spread = x.std(ddof=1)
    return math.nan if spread == 0 else float(x.mean() / spread * math.sqrt(periods_per_year))


def profit_factor(pnl: Numbers) -> float:
    """Gross profit over gross loss; infinite with wins and no losses, NaN with no trades."""
    x = np.asarray(pnl, dtype=float)
    wins, losses = float(x[x > 0].sum()), float(-x[x < 0].sum())
    if losses == 0:
        return math.inf if wins > 0 else math.nan
    return wins / losses


def max_drawdown(equity: pd.Series) -> tuple[float, float]:
    """The largest fall from a running peak: (amount, percent of that peak), both >= 0."""
    if equity.empty:
        return 0.0, 0.0
    peak = equity.cummax()
    fall = peak - equity
    worst = int(np.argmax(fall.to_numpy()))
    amount = float(fall.iloc[worst])
    base = float(peak.iloc[worst])
    return amount, (100.0 * amount / base if base > 0 else math.nan)


def daily_equity(equity: pd.Series) -> pd.Series:
    """The last equity value of each calendar day."""
    stamps = pd.DatetimeIndex(equity.index)
    return equity.groupby(stamps.normalize()).last()
