"""Shared constants, helpers and test strategies (fixtures live in conftest.py)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd

from quant_engine.core import IST, Bar, Fill, Order, Side, SimulatedClock
from quant_engine.data import ExchangeCalendar
from quant_engine.execution import (
    BarQuotes,
    ChasePolicy,
    LiveConfig,
    LiveRunner,
    OrderExecutor,
    ReplayFeed,
    SimulatedBroker,
    StateStore,
)
from quant_engine.strategy import Strategy, StrategyContext

MONDAY = dt.date(2026, 1, 5)
TUESDAY = dt.date(2026, 1, 6)
SYMBOL = "NFO:FUT"
CALENDAR = ExchangeCalendar.nse()
FAST_CHASE = ChasePolicy(wait_s=0.5, poll_s=0.1, max_reprices=2)

BarFactory = Callable[..., pd.DataFrame]
BarAction = Callable[[Bar, StrategyContext], object]
FillAction = Callable[[Fill, StrategyContext], object]


def ohlc_bars(
    rows: Sequence[tuple[float, float, float, float]],
    day: dt.date = MONDAY,
    start: str = "09:15",
    minutes: int = 1,
) -> pd.DataFrame:
    """Bars from explicit (open, high, low, close) rows, ready for the backtester."""
    first = pd.Timestamp.combine(day, dt.time.fromisoformat(start)).tz_localize(IST)
    index = pd.date_range(first, periods=len(rows), freq=f"{minutes}min")
    frame = pd.DataFrame(list(rows), columns=["open", "high", "low", "close"], index=index)
    frame = frame.astype(float)
    frame["volume"] = 100.0
    frame["available_at"] = index + pd.Timedelta(minutes=minutes)
    return frame


class Scripted(Strategy):
    """Runs ``at[n]`` on the n-th bar it sees and ``on_fill_do`` on every fill; records it all."""

    def __init__(
        self, at: dict[int, BarAction] | None = None, on_fill_do: FillAction | None = None
    ) -> None:
        self.at = at or {}
        self.on_fill_do = on_fill_do
        self.seen: list[dict[str, object]] = []
        self.fills: list[Fill] = []

    def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        history = ctx.history()
        self.seen.append(
            {
                "start": bar.start,
                "now": ctx.now,
                "history_rows": len(history),
                "history_last": history.index[-1],
                "position": ctx.position,
                "session_end": ctx.is_session_end,
            }
        )
        action = self.at.get(len(self.seen) - 1)
        if action is not None:
            action(bar, ctx)

    def on_fill(self, fill: Fill, ctx: StrategyContext) -> None:
        self.fills.append(fill)
        if self.on_fill_do is not None:
            self.on_fill_do(fill, ctx)


def buy(qty: float) -> BarAction:
    return lambda bar, ctx: ctx.submit(Order.market(Side.BUY, qty))


def until(bars: pd.DataFrame) -> pd.Timestamp:
    """Just after the last bar becomes available."""
    return pd.Timestamp(bars["available_at"].iloc[-1]) + pd.Timedelta(seconds=1)


def live_book(
    tmp_path: Path,
    strategy: Strategy,
    bars: pd.DataFrame,
    *,
    broker: SimulatedBroker | None = None,
    backstop_pct: float | None = None,
) -> tuple[LiveRunner, SimulatedBroker, SimulatedClock, StateStore]:
    """A live runner replaying ``bars`` against a simulated broker quoting their closes."""
    clock = SimulatedClock(bars.index[0].to_pydatetime())
    feed = ReplayFeed(bars)
    quotes = BarQuotes(feed, clock, SYMBOL, half_spread=0.05)
    broker = broker or SimulatedBroker(quotes)
    broker.quotes = quotes
    state = StateStore(tmp_path / "book.json", clock)
    runner = LiveRunner(
        strategy,
        feed,
        broker,
        OrderExecutor(broker, clock, FAST_CHASE),
        CALENDAR,
        state,
        LiveConfig(SYMBOL, poll_s=1.0, backstop_pct=backstop_pct),
        clock,
    )
    return runner, broker, clock, state
