"""A synthetic minute-bar market with the features real index data has and a random walk lacks.

Used by the tests and examples, so neither needs vendor data. The model, per trading day ``d``:

* **Volatility clustering.** Daily variance follows a GARCH(1,1) process,
  ``s2[d] = w + alpha * shock[d-1]**2 + beta * s2[d-1]``, reverting to the long-run level set by
  ``annual_vol``. Calm and turbulent stretches persist the way they do in real markets.
* **Overnight gaps.** A share of each day's variance arrives between the close and the next open.
* **Intraday U-shape.** Minute variance is highest at the open and the close and lowest at midday.
* **Fat tails.** Shocks are Student-t (unit variance) rather than normal.
* **Valid bars.** Highs and lows extend beyond the open-close body, prices sit on the tick grid,
  and volume rises with the size of the move.

The same seed and date range always give the same bars.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
import pandas as pd

from quant_engine.data.calendar import ExchangeCalendar

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class SyntheticConfig:
    start_price: float = 20_000.0
    annual_drift: float = 0.08  # drift of the log price per year
    annual_vol: float = 0.14  # long-run volatility the GARCH process reverts to
    garch_alpha: float = 0.08  # weight of yesterday's shock in today's variance
    garch_beta: float = 0.90  # persistence of variance
    overnight_share: float = 0.20  # share of daily variance that arrives as the opening gap
    u_shape: float = 2.0  # first and last minutes carry (1 + u_shape)x midday variance
    tail_dof: float | None = 5.0  # Student-t degrees of freedom; None for normal shocks
    wick_scale: float = 0.5  # typical high/low extension beyond the body, in minute sigmas
    tick: float = 0.05
    base_volume: float = 5_000.0  # average volume per minute
    days_per_year: int = 250

    def __post_init__(self) -> None:
        if self.start_price <= 0 or self.annual_vol <= 0 or self.tick <= 0:
            raise ValueError("start_price, annual_vol and tick must be positive")
        if self.garch_alpha < 0 or self.garch_beta < 0 or self.garch_alpha + self.garch_beta >= 1:
            raise ValueError("GARCH needs alpha, beta >= 0 and alpha + beta < 1 to be stationary")
        if not 0 <= self.overnight_share < 1:
            raise ValueError("overnight_share must be in [0, 1)")
        if self.tail_dof is not None and self.tail_dof <= 2:
            raise ValueError("tail_dof must exceed 2 for the shocks to have a variance")


@dataclass
class SyntheticMarket:
    calendar: ExchangeCalendar
    config: SyntheticConfig = field(default_factory=SyntheticConfig)
    seed: int | None = None

    def _shocks(self, rng: np.random.Generator, size: int | tuple[int, ...]) -> FloatArray:
        dof = self.config.tail_dof
        if dof is None:
            return rng.standard_normal(size)
        scaled: FloatArray = rng.standard_t(dof, size) * np.sqrt((dof - 2) / dof)
        return scaled

    def _minute_weights(self, minutes: int) -> FloatArray:
        position = (np.arange(minutes) + 0.5) / minutes
        raw = 1.0 + self.config.u_shape * (2.0 * position - 1.0) ** 2
        weights: FloatArray = raw / raw.sum()
        return weights

    def minute_bars(self, start: dt.date, end: dt.date) -> pd.DataFrame:
        """OHLCV minute bars for every trading day from ``start`` to ``end``."""
        cfg = self.config
        index = self.calendar.minute_index(start, end)
        n_minutes = self.calendar.session.minutes
        n_days = len(index) // n_minutes
        if n_days == 0:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"], index=index)

        rng = np.random.default_rng(self.seed)
        weights = self._minute_weights(n_minutes)
        long_run = cfg.annual_vol**2 / cfg.days_per_year
        omega = (1.0 - cfg.garch_alpha - cfg.garch_beta) * long_run
        drift = cfg.annual_drift / cfg.days_per_year
        intraday_share = 1.0 - cfg.overnight_share

        returns = np.empty((n_days, n_minutes))
        gaps = np.empty(n_days)
        minute_sigma = np.empty((n_days, n_minutes))
        variance = long_run
        for d in range(n_days):
            sigma = np.sqrt(intraday_share * variance * weights)
            gaps[d] = (
                drift * cfg.overnight_share
                + np.sqrt(cfg.overnight_share * variance) * self._shocks(rng, 1)[0]
            )
            returns[d] = drift * intraday_share * weights + sigma * self._shocks(rng, n_minutes)
            minute_sigma[d] = sigma
            shock = gaps[d] + returns[d].sum() - drift
            variance = omega + cfg.garch_alpha * shock**2 + cfg.garch_beta * variance

        log_open = np.log(cfg.start_price) + np.cumsum(gaps + np.r_[0.0, returns.sum(axis=1)[:-1]])
        log_close = log_open[:, None] + np.cumsum(returns, axis=1)
        log_bar_open = np.concatenate([log_open[:, None], log_close[:, :-1]], axis=1)

        bar_open, bar_close = np.exp(log_bar_open), np.exp(log_close)
        wick_up = np.abs(rng.standard_normal(returns.shape)) * minute_sigma * cfg.wick_scale
        wick_down = np.abs(rng.standard_normal(returns.shape)) * minute_sigma * cfg.wick_scale
        bar_high = np.maximum(bar_open, bar_close) * np.exp(wick_up)
        bar_low = np.minimum(bar_open, bar_close) * np.exp(-wick_down)

        activity = 0.5 + 0.5 * np.abs(returns) / minute_sigma
        noise = np.exp(rng.normal(0.0, 0.25, returns.shape))
        volume = np.rint(cfg.base_volume * weights * n_minutes * activity * noise)

        def on_ticks(prices: FloatArray) -> FloatArray:
            # Rounding is monotone, so high >= max(open, close) >= min(open, close) >= low survives.
            rounded: FloatArray = np.round(np.round(prices / cfg.tick) * cfg.tick, 6)
            return rounded.ravel()

        return pd.DataFrame(
            {
                "open": on_ticks(bar_open),
                "high": on_ticks(bar_high),
                "low": on_ticks(bar_low),
                "close": on_ticks(bar_close),
                "volume": volume.ravel().astype(np.int64),
            },
            index=index,
        )
