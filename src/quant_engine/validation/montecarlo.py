"""Monte Carlo resampling of a trade sequence.

A backtest yields one path: one ordering of its trades, one maximum drawdown, one longest losing
streak. Live trading draws another path from the same distribution. Resampling the trades (with
replacement) many times shows the range of paths the same edge could have produced, which is what
position sizing and a loss limit should be set against.

Independent resampling assumes trades do not cluster. When losses come in bunches (one regime, one
volatility spell), use ``block`` > 1: a circular block bootstrap keeps runs of neighbouring trades
together and gives wider, more honest drawdown tails.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


def bootstrap_indices(
    n_obs: int, n_draws: int, n_paths: int, rng: np.random.Generator, block: int = 1
) -> IntArray:
    """Indices into a sequence of ``n_obs`` for ``n_paths`` resampled paths of ``n_draws`` each.

    With ``block`` > 1, paths are built from runs of ``block`` consecutive observations starting at
    random points, wrapping round the end (circular block bootstrap).
    """
    if n_obs < 1 or n_draws < 1 or n_paths < 1 or block < 1:
        raise ValueError("n_obs, n_draws, n_paths and block must be positive")
    blocks = -(-n_draws // block)
    starts = rng.integers(0, n_obs, size=(n_paths, blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n_obs
    result: IntArray = idx.reshape(n_paths, blocks * block)[:, :n_draws].astype(np.int64)
    return result


def longest_run(mask: npt.NDArray[np.bool_]) -> IntArray:
    """Per row, the length of the longest run of True values."""
    n = mask.shape[1]
    position = np.arange(n)
    last_false = np.maximum.accumulate(np.where(~mask, position, -1), axis=1)
    runs = np.where(mask, position - last_false, 0)
    result: IntArray = runs.max(axis=1).astype(np.int64)
    return result


@dataclass(frozen=True)
class MonteCarloReport:
    final_return_pct: FloatArray
    max_drawdown_pct: FloatArray
    longest_losing_streak: IntArray
    ruin_drawdown_pct: float

    @property
    def paths(self) -> int:
        return len(self.final_return_pct)

    @property
    def ruin_probability(self) -> float:
        """The share of paths whose drawdown reached ``ruin_drawdown_pct``."""
        return float(np.mean(self.max_drawdown_pct >= self.ruin_drawdown_pct))

    def percentiles(self, q: Sequence[float] = (5, 25, 50, 75, 95)) -> pd.DataFrame:
        metrics = {
            "final_return_pct": self.final_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "longest_losing_streak": self.longest_losing_streak,
        }
        return pd.DataFrame(
            {name: np.percentile(values, q) for name, values in metrics.items()},
            index=[f"p{int(x)}" for x in q],
        ).T


def resample_trades(
    trade_returns_pct: Sequence[float],
    *,
    n_paths: int = 10_000,
    n_trades: int | None = None,
    block: int = 1,
    capital_fraction: float = 1.0,
    ruin_drawdown_pct: float = 50.0,
    seed: int | None = None,
) -> MonteCarloReport:
    """Compound resampled trades into equity paths and measure each path.

    ``trade_returns_pct`` are per-trade net returns in % of the position's notional; each moves the
    account by ``capital_fraction`` of that (the share of equity committed per trade).
    """
    returns = np.asarray(trade_returns_pct, dtype=float)
    if returns.size == 0:
        raise ValueError("no trades to resample")
    draws = n_trades or returns.size
    rng = np.random.default_rng(seed)
    idx = bootstrap_indices(returns.size, draws, n_paths, rng, block)
    account = returns[idx] / 100.0 * capital_fraction

    equity = np.cumprod(1.0 + account, axis=1)
    with_start = np.concatenate([np.ones((n_paths, 1)), equity], axis=1)
    peak = np.maximum.accumulate(with_start, axis=1)
    drawdown = 100.0 * (1.0 - with_start / peak)
    # np.asarray pins the dtype for type checkers: NumPy versions differ in what they infer here.
    return MonteCarloReport(
        final_return_pct=np.asarray(100.0 * (equity[:, -1] - 1.0), dtype=np.float64),
        max_drawdown_pct=np.asarray(drawdown.max(axis=1), dtype=np.float64),
        longest_losing_streak=longest_run(account < 0),
        ruin_drawdown_pct=ruin_drawdown_pct,
    )
