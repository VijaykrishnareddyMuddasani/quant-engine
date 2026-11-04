import math

import pandas as pd
import pytest

from quant_engine.backtest.metrics import (
    daily_equity,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    t_statistic,
)


def test_t_statistic() -> None:
    assert t_statistic([1.0, 2.0, 3.0]) == pytest.approx(2.0 / (1.0 / math.sqrt(3)))
    assert math.isnan(t_statistic([1.0]))
    assert math.isnan(t_statistic([2.0, 2.0]))


def test_sharpe_ratio_is_annualised() -> None:
    returns = [0.01, -0.01, 0.02, 0.0]
    mean, sd = 0.005, pd.Series(returns).std()
    assert sharpe_ratio(returns, periods_per_year=250) == pytest.approx(mean / sd * math.sqrt(250))


def test_profit_factor_edges() -> None:
    assert profit_factor([30.0, -10.0, -5.0]) == pytest.approx(2.0)
    assert profit_factor([5.0]) == math.inf
    assert math.isnan(profit_factor([]))


def test_max_drawdown_is_measured_from_the_running_peak() -> None:
    equity = pd.Series([100.0, 120.0, 90.0, 130.0, 117.0])
    amount, pct = max_drawdown(equity)
    assert amount == 30.0
    assert pct == pytest.approx(25.0)
    assert max_drawdown(pd.Series(dtype=float)) == (0.0, 0.0)


def test_daily_equity_keeps_each_days_last_value() -> None:
    stamps = pd.to_datetime(
        ["2026-01-05 10:00", "2026-01-05 12:00", "2026-01-06 10:00"]
    ).tz_localize("Asia/Kolkata")
    daily = daily_equity(pd.Series([1.0, 2.0, 3.0], index=stamps))
    assert daily.tolist() == [2.0, 3.0]
