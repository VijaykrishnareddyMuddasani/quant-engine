"""Value types shared by the backtester and the live engine: bars, orders, fills and trades.

All of them are immutable. An ``Order`` is a request; the engine that accepts it hands back an id
and owns everything that happens next.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass

import pandas as pd


class Side(enum.IntEnum):
    BUY = 1
    SELL = -1

    @property
    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY

    @classmethod
    def of(cls, signed_quantity: float) -> Side:
        """The side that moves a position by ``signed_quantity`` (which must not be zero)."""
        if signed_quantity == 0:
            raise ValueError("a zero quantity has no side")
        return cls.BUY if signed_quantity > 0 else cls.SELL


class OrderType(enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


@dataclass(frozen=True)
class Bar:
    """One completed bar. ``available_at`` is the earliest moment a decision may use it."""

    start: pd.Timestamp
    available_at: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Order:
    """A request to trade ``quantity`` units (always positive; ``side`` gives the direction).

    ``price`` is the limit price of a LIMIT order and the trigger of a STOP order. A DAY order is
    cancelled at the end of the session it was placed in; ``good_till_cancelled`` keeps it working.
    Orders sharing an ``oco`` group cancel each other: when one fills, the rest are withdrawn, which
    is how a stop and a target bracket one position.
    """

    side: Side
    quantity: float
    type: OrderType = OrderType.MARKET
    price: float | None = None
    tag: str = ""
    oco: str | None = None
    good_till_cancelled: bool = False

    def __post_init__(self) -> None:
        if not math.isfinite(self.quantity) or self.quantity <= 0:
            raise ValueError(f"order quantity must be positive, got {self.quantity}")
        if self.type is OrderType.MARKET:
            if self.price is not None:
                raise ValueError("a market order takes no price")
        elif self.price is None or not math.isfinite(self.price) or self.price <= 0:
            raise ValueError(f"a {self.type.value} order needs a positive price")

    @classmethod
    def market(
        cls, side: Side, quantity: float, *, tag: str = "", good_till_cancelled: bool = False
    ) -> Order:
        return cls(side, quantity, tag=tag, good_till_cancelled=good_till_cancelled)

    @classmethod
    def limit(
        cls,
        side: Side,
        quantity: float,
        price: float,
        *,
        tag: str = "",
        oco: str | None = None,
        good_till_cancelled: bool = False,
    ) -> Order:
        return cls(side, quantity, OrderType.LIMIT, price, tag, oco, good_till_cancelled)

    @classmethod
    def stop(
        cls,
        side: Side,
        quantity: float,
        trigger: float,
        *,
        tag: str = "",
        oco: str | None = None,
        good_till_cancelled: bool = False,
    ) -> Order:
        return cls(side, quantity, OrderType.STOP, trigger, tag, oco, good_till_cancelled)


@dataclass(frozen=True)
class WorkingOrder:
    """An accepted order that has not filled or been cancelled yet."""

    id: int
    order: Order
    submitted_at: pd.Timestamp


@dataclass(frozen=True)
class Fill:
    order_id: int
    time: pd.Timestamp
    side: Side
    quantity: float
    price: float
    cost: float
    tag: str = ""

    @property
    def signed_quantity(self) -> float:
        return self.side * self.quantity


@dataclass(frozen=True)
class Trade:
    """A round trip: from flat, through any adds and partial exits, back to flat.

    Prices are quantity-weighted averages of the entry and exit fills. ``costs`` holds every charge
    on those fills, so ``net_pnl = gross_pnl - costs``.
    """

    direction: int
    quantity: float
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    gross_pnl: float
    costs: float
    bars_held: int
    entry_tag: str = ""
    exit_tag: str = ""

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.costs

    @property
    def notional(self) -> float:
        return self.entry_price * self.quantity

    @property
    def gross_return_pct(self) -> float:
        """The move captured, in % of the entry price, before costs."""
        return 100.0 * self.gross_pnl / self.notional

    @property
    def net_return_pct(self) -> float:
        return 100.0 * self.net_pnl / self.notional
