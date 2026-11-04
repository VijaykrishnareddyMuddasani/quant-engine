"""The broker boundary: the types every broker speaks, and the protocol each one implements.

The error types matter more than the methods. A broker call can fail in three ways that call for
three different responses:

* ``OrderRejected``: the broker said no. Nothing happened; do not retry the same request.
* ``BrokerUnavailable``: the call failed before reaching the broker. Nothing happened; retrying is
  safe.
* ``OutcomeUnknown``: the request may have reached the broker (a timeout after sending). Retrying
  blindly can double a position, so the order must be looked for first.
"""

from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass
from typing import Protocol

from quant_engine.core.types import Side


class BrokerOrderType(enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LIMIT = "SL"
    STOP_MARKET = "SL-M"


class OrderStatus(enum.Enum):
    OPEN = "OPEN"
    TRIGGER_PENDING = "TRIGGER PENDING"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

    @property
    def is_final(self) -> bool:
        return self in {OrderStatus.COMPLETE, OrderStatus.CANCELLED, OrderStatus.REJECTED}


@dataclass(frozen=True)
class OrderRequest:
    """``symbol`` is exchange-qualified (``NFO:...``). ``tag`` must be unique per request: it is
    how an order whose placement response was lost gets found again."""

    symbol: str
    side: Side
    quantity: int
    order_type: BrokerOrderType = BrokerOrderType.LIMIT
    price: float | None = None
    trigger: float | None = None
    product: str = "MIS"
    tag: str = ""

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        needs_price = self.order_type in {BrokerOrderType.LIMIT, BrokerOrderType.STOP_LIMIT}
        if needs_price and (self.price is None or self.price <= 0):
            raise ValueError(f"a {self.order_type.value} order needs a positive price")
        needs_trigger = self.order_type in {BrokerOrderType.STOP_LIMIT, BrokerOrderType.STOP_MARKET}
        if needs_trigger and (self.trigger is None or self.trigger <= 0):
            raise ValueError(f"a {self.order_type.value} order needs a trigger")


@dataclass(frozen=True)
class OrderState:
    order_id: str
    request: OrderRequest
    status: OrderStatus
    filled_quantity: int = 0
    average_price: float = 0.0
    message: str = ""


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float | None
    ask: float | None
    last: float
    time: dt.datetime

    def touch(self, side: Side) -> float | None:
        """The price an order on ``side`` would take now: the ask to buy, the bid to sell."""
        return self.ask if side is Side.BUY else self.bid


class BrokerError(Exception):
    """Any failure talking to the broker."""


class OrderRejected(BrokerError):
    """The broker refused the request. Nothing happened."""


class BrokerUnavailable(BrokerError):
    """The call never reached the broker. Nothing happened; it is safe to retry."""


class OutcomeUnknown(BrokerError):
    """The request may or may not have reached the broker. Look before retrying."""


class Broker(Protocol):
    def place(self, request: OrderRequest) -> str:
        """Send an order; returns the broker's order id."""
        ...

    def modify(self, order_id: str, price: float) -> None: ...

    def cancel(self, order_id: str) -> None: ...

    def order(self, order_id: str) -> OrderState: ...

    def orders(self) -> list[OrderState]:
        """Today's orders, so a lost placement can be found by its tag."""
        ...

    def positions(self) -> dict[str, int]:
        """Net quantity per exchange-qualified symbol (positive long, negative short)."""
        ...

    def quote(self, symbol: str) -> Quote: ...
