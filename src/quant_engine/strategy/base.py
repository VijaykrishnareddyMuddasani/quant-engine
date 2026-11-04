"""The Strategy interface: all a strategy, public or private, has to implement.

A strategy sees the market only through a ``StrategyContext``. The backtester provides one context
and the live engine another, and the strategy cannot tell them apart. That is what makes a backtest
a statement about the code that will trade, rather than about a re-implementation of it.

Rules for strategy authors:

* Keep state on ``self``. Read prices only through ``bar`` and ``ctx.history``; both stop at the
  bar that has just completed, so there is no future to peek at.
* Orders placed in ``on_bar`` can fill from the *next* bar onwards, never on the bar that caused
  them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

import pandas as pd

from quant_engine.core.types import Bar, Fill, Order, Side, WorkingOrder


class StrategyContext(Protocol):
    """What a strategy may ask of the engine running it."""

    @property
    def now(self) -> pd.Timestamp:
        """The moment of the decision: the current bar's ``available_at``."""
        ...

    @property
    def position(self) -> float:
        """Units held: positive long, negative short, zero flat."""
        ...

    @property
    def working_orders(self) -> tuple[WorkingOrder, ...]: ...

    @property
    def is_session_end(self) -> bool:
        """Whether the current bar is the last one of its trading session."""
        ...

    def history(self, bars: int | None = None) -> pd.DataFrame:
        """The last ``bars`` completed bars (all of them if None), the current one included."""
        ...

    def submit(self, order: Order) -> int:
        """Place an order; returns its id."""
        ...

    def cancel(self, order_id: int) -> None: ...

    def cancel_all(self) -> None: ...


class Strategy(ABC):
    """Base class for strategies. Only ``on_bar`` is required."""

    @property
    def name(self) -> str:
        return type(self).__name__

    def on_start(self, ctx: StrategyContext) -> None:  # noqa: B027 - optional hook
        """Called once before the first bar."""

    @abstractmethod
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        """Called once for every completed bar, in time order."""

    def on_fill(self, fill: Fill, ctx: StrategyContext) -> None:  # noqa: B027 - optional hook
        """Called for each fill of this strategy's orders, before the next ``on_bar``."""

    def on_finish(self, ctx: StrategyContext) -> None:  # noqa: B027 - optional hook
        """Called once after the last bar."""


def trade_to(ctx: StrategyContext, target: float, *, tag: str = "") -> int | None:
    """Send the market order that takes the position to ``target`` units; None if already there."""
    difference = target - ctx.position
    if difference == 0:
        return None
    return ctx.submit(Order.market(Side.of(difference), abs(difference), tag=tag))
