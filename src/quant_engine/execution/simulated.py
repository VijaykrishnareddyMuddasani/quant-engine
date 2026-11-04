"""A broker that fills against quotes in memory: paper trading, and the failures tests need.

With live quotes it is a paper broker: real prices, no real orders. With ``StaticQuotes`` it is a
test double, and ``inject`` makes the next placement fail the way real brokers fail - a
rejection, an outage, or a timeout *after* the order was accepted.
"""

from __future__ import annotations

import enum
import itertools
from collections import deque
from dataclasses import dataclass, replace
from typing import Protocol

from quant_engine.core.clock import Clock
from quant_engine.core.types import Side
from quant_engine.execution.broker import (
    BrokerOrderType,
    BrokerUnavailable,
    OrderRejected,
    OrderRequest,
    OrderState,
    OrderStatus,
    OutcomeUnknown,
    Quote,
)


class QuoteSource(Protocol):
    def quote(self, symbol: str) -> Quote: ...


class StaticQuotes:
    """Quotes set by hand."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self._quotes: dict[str, tuple[float | None, float | None, float]] = {}

    def set(
        self, symbol: str, bid: float | None, ask: float | None, last: float | None = None
    ) -> None:
        mid = last if last is not None else ((bid or 0.0) + (ask or 0.0)) / 2
        self._quotes[symbol] = (bid, ask, mid)

    def quote(self, symbol: str) -> Quote:
        if symbol not in self._quotes:
            raise OrderRejected(f"no quote for {symbol}")
        bid, ask, last = self._quotes[symbol]
        return Quote(symbol, bid, ask, last, self.clock.now())


class Fault(enum.Enum):
    REJECT = "reject"  # the broker refuses the order
    UNAVAILABLE = "unavailable"  # the call never arrives
    TIMEOUT_AFTER_ACCEPT = "timeout"  # the order is live, but the caller hears only a timeout


@dataclass
class _Order:
    state: OrderState
    price: float | None
    triggered: bool = False


class SimulatedBroker:
    def __init__(self, quotes: QuoteSource, *, fill_limit: int | None = None) -> None:
        """``fill_limit`` caps the quantity filled per check, to simulate partial fills."""
        self.quotes = quotes
        self.fill_limit = fill_limit
        self.fills_enabled = True
        self._orders: dict[str, _Order] = {}
        self._positions: dict[str, int] = {}
        self._faults: deque[Fault] = deque()
        self._ids = itertools.count(1)
        self.placed: list[OrderRequest] = []

    def inject(self, *faults: Fault) -> None:
        """Make the next placements fail, one fault per placement, in order."""
        self._faults.extend(faults)

    # --- Broker -------------------------------------------------------------------------------

    def place(self, request: OrderRequest) -> str:
        fault = self._faults.popleft() if self._faults else None
        if fault is Fault.UNAVAILABLE:
            raise BrokerUnavailable("simulated outage")
        if fault is Fault.REJECT:
            raise OrderRejected("simulated rejection")
        order_id = f"SIM{next(self._ids)}"
        state = OrderState(order_id, request, OrderStatus.OPEN)
        if request.order_type in {BrokerOrderType.STOP_LIMIT, BrokerOrderType.STOP_MARKET}:
            state = replace(state, status=OrderStatus.TRIGGER_PENDING)
        self._orders[order_id] = _Order(state, request.price)
        self.placed.append(request)
        self._try_fill(order_id)
        if fault is Fault.TIMEOUT_AFTER_ACCEPT:
            raise OutcomeUnknown("simulated timeout after the order was accepted")
        return order_id

    def modify(self, order_id: str, price: float) -> None:
        order = self._get(order_id)
        if order.state.status.is_final:
            raise OrderRejected(f"{order_id} is {order.state.status.value}")
        order.price = price
        self._try_fill(order_id)

    def cancel(self, order_id: str) -> None:
        order = self._get(order_id)
        if not order.state.status.is_final:
            order.state = replace(order.state, status=OrderStatus.CANCELLED)

    def order(self, order_id: str) -> OrderState:
        self._try_fill(order_id)
        return self._get(order_id).state

    def orders(self) -> list[OrderState]:
        return [self.order(order_id) for order_id in self._orders]

    def positions(self) -> dict[str, int]:
        return {s: q for s, q in self._positions.items() if q != 0}

    def quote(self, symbol: str) -> Quote:
        return self.quotes.quote(symbol)

    # --- matching -----------------------------------------------------------------------------

    def _get(self, order_id: str) -> _Order:
        try:
            return self._orders[order_id]
        except KeyError:
            raise OrderRejected(f"unknown order {order_id}") from None

    def _try_fill(self, order_id: str) -> None:
        order = self._orders[order_id]
        state, request = order.state, order.state.request
        if state.status.is_final or not self.fills_enabled:
            return
        quote = self.quotes.quote(request.symbol)
        if not order.triggered and state.status is OrderStatus.TRIGGER_PENDING:
            trigger = request.trigger
            if trigger is None:  # OrderRequest refuses this; the check narrows the type
                return
            hit = quote.last >= trigger if request.side is Side.BUY else quote.last <= trigger
            if not hit:
                return
            order.triggered = True
            order.state = replace(state, status=OrderStatus.OPEN)
        touch = quote.touch(request.side)
        if touch is None:
            return
        market = request.order_type in {BrokerOrderType.MARKET, BrokerOrderType.STOP_MARKET}
        limit = order.price
        marketable = market or (
            limit is not None and (touch <= limit if request.side is Side.BUY else touch >= limit)
        )
        if not marketable:
            return
        remaining = request.quantity - order.state.filled_quantity
        quantity = min(remaining, self.fill_limit or remaining)
        filled = order.state.filled_quantity + quantity
        average = (
            order.state.average_price * order.state.filled_quantity + touch * quantity
        ) / filled
        order.state = replace(
            order.state,
            filled_quantity=filled,
            average_price=average,
            status=OrderStatus.COMPLETE if filled == request.quantity else OrderStatus.OPEN,
        )
        self._positions[request.symbol] = self._positions.get(request.symbol, 0) + int(
            request.side * quantity
        )
