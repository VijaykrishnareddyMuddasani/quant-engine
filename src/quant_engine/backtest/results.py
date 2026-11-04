"""What a backtest returns: its trades, fills, equity curve and a summary."""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_engine.backtest.metrics import (
    daily_equity,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    t_statistic,
)
from quant_engine.core.types import Fill, Trade

TRADE_COLUMNS = [f.name for f in dataclasses.fields(Trade)] + [
    "net_pnl",
    "gross_return_pct",
    "net_return_pct",
]
FILL_COLUMNS = [f.name for f in dataclasses.fields(Fill)]


def trades_frame(trades: list[Trade]) -> pd.DataFrame:
    rows = [
        {
            **dataclasses.asdict(t),
            "net_pnl": t.net_pnl,
            "gross_return_pct": t.gross_return_pct,
            "net_return_pct": t.net_return_pct,
        }
        for t in trades
    ]
    return pd.DataFrame(rows, columns=TRADE_COLUMNS)


def fills_frame(fills: list[Fill]) -> pd.DataFrame:
    rows = [{**dataclasses.asdict(f), "side": f.side.name} for f in fills]
    return pd.DataFrame(rows, columns=FILL_COLUMNS)


@dataclass(frozen=True)
class BacktestResult:
    """``equity`` and ``position`` are the state after each bar, indexed by its ``available_at``."""

    strategy: str
    initial_capital: float
    trades: pd.DataFrame
    fills: pd.DataFrame
    equity: pd.Series
    position: pd.Series
    skipped_bars: int = 0

    def daily_returns(self) -> pd.Series:
        daily = daily_equity(self.equity)
        return daily / daily.shift(1, fill_value=self.initial_capital) - 1.0

    def summary(self) -> dict[str, float]:
        net = self.trades["net_return_pct"]
        curve = pd.concat([pd.Series([self.initial_capital]), self.equity.reset_index(drop=True)])
        _, drawdown_pct = max_drawdown(curve.reset_index(drop=True))
        final = float(self.equity.iloc[-1]) if len(self.equity) else self.initial_capital
        exposure = float(np.mean(self.position.to_numpy() != 0)) if len(self.position) else 0.0
        return {
            "trades": float(len(self.trades)),
            "win_rate_pct": 100.0 * float((self.trades["net_pnl"] > 0).mean())
            if len(self.trades)
            else math.nan,
            "avg_net_return_pct": float(net.mean()) if len(net) else math.nan,
            "t_stat": t_statistic(net),
            "profit_factor": profit_factor(self.trades["net_pnl"]),
            "net_pnl": float(self.trades["net_pnl"].sum()),
            "costs": float(self.trades["costs"].sum()),
            "total_return_pct": 100.0 * (final / self.initial_capital - 1.0),
            "max_drawdown_pct": drawdown_pct,
            "sharpe": sharpe_ratio(self.daily_returns()),
            "exposure_pct": 100.0 * exposure,
            "avg_bars_held": float(self.trades["bars_held"].mean())
            if len(self.trades)
            else math.nan,
        }

    def report(self) -> str:
        s = self.summary()
        lines = [
            f"{self.strategy}",
            f"  trades            {s['trades']:>12.0f}",
            f"  win rate          {s['win_rate_pct']:>11.1f}%",
            f"  avg trade (net)   {s['avg_net_return_pct']:>11.3f}%   t {s['t_stat']:.2f}",
            f"  profit factor     {s['profit_factor']:>12.2f}",
            f"  net P&L           {s['net_pnl']:>12,.0f}   after costs of {s['costs']:,.0f}",
            f"  total return      {s['total_return_pct']:>11.2f}%",
            f"  max drawdown      {s['max_drawdown_pct']:>11.2f}%",
            f"  Sharpe (daily)    {s['sharpe']:>12.2f}",
            f"  time in market    {s['exposure_pct']:>11.1f}%",
        ]
        if self.skipped_bars:
            lines.append(f"  blank bars skipped {self.skipped_bars:>11d}")
        return "\n".join(lines)
