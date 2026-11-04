"""Getting filled without paying the spread twice, and without ever doubling a position.

``OrderExecutor.execute`` works a limit order at the touch (the ask to buy, the bid to sell),
re-pricing it to the new touch every ``wait_s`` seconds for at most ``max_reprices`` rounds, and
gives up if the market runs more than ``max_slippage_pct`` away from where it started. What is
filled when it stops is reported, never hidden: a partial fill is a partial fill.

Placement is idempotent. Each request carries a unique tag. If placing raises ``OutcomeUnknown``,
the executor looks for an order with that tag before doing anything else. If it cannot find one,
it halts rather than place again, because "not found yet" is not "not there" and a second order
would be a second position.
"""

from __future__ import annotations

import contextlib
import itertools
from collections.abc import Iterable
from dataclasses import dataclass

from quant_engine.core.clock import Clock
from quant_engine.core.types import Side
from quant_engine.execution.broker import (
    Broker,
    BrokerOrderType,
    BrokerUnavailable,
    OrderRejected,
    OrderRequest,
    OrderState,
    OrderStatus,
    OutcomeUnknown,
)


class ExecutionHalted(RuntimeError):
    """The executor cannot tell what the broker holds. A person has to look."""


@dataclass(frozen=True)
class ChasePolicy:
    wait_s: float = 2.0  # how long a price is given before re-pricing
    poll_s: float = 0.2  # how often the order is read while waiting
    max_reprices: int = 6  # stay well under the broker's cap on modifications per order
    max_slippage_pct: float = 3.0  # stop chasing once the touch is this far from the first one
    retries_when_unavailable: int = 3  # placements retried when the call never arrived
    lookups_when_unknown: int = 10  # reads spent looking for a placement whose reply was lost
    settle_timeout_s: float = 10.0  # how long to wait for a cancel to become final


@dataclass(frozen=True)
class Execution:
    symbol: str
    side: Side
    requested: int
    filled: int
    average_price: float
    order_ids: tuple[str, ...]
    reason: str = ""

    @property
    def complete(self) -> bool:
        return self.filled == self.requested


class OrderExecutor:
    def __init__(
        self,
        broker: Broker,
        clock: Clock,
        policy: ChasePolicy | None = None,
        tag_prefix: str = "qe",
    ) -> None:
        self.broker = broker
        self.clock = clock
        self.policy = policy or ChasePolicy()
        self.tag_prefix = tag_prefix
        self._sequence = itertools.count(1)

    def new_tag(self) -> str:
        """Unique within a day and across restarts: prefix, time of day, sequence (<= 20 chars)."""
        return f"{self.tag_prefix}{self.clock.now():%H%M%S}{next(self._sequence) % 1000:03d}"

    # --- placing exactly once -----------------------------------------------------------------

    def place_once(self, request: OrderRequest) -> str:
        for attempt in itertools.count():
            try:
                return self.broker.place(request)
            except BrokerUnavailable:
                if attempt >= self.policy.retries_when_unavailable:
                    raise
                self.clock.sleep(self.policy.poll_s)
            except OutcomeUnknown:
                return self._find_by_tag(request)
        raise AssertionError("unreachable")  # pragma: no cover

    def _find_by_tag(self, request: OrderRequest) -> str:
        for _ in range(self.policy.lookups_when_unknown):
            self.clock.sleep(self.policy.poll_s)
            try:
                found = [o for o in self.broker.orders() if o.request.tag == request.tag]
            except BrokerUnavailable:
                continue
            if found:
                return found[0].order_id
        raise ExecutionHalted(
            f"placement of {request.side.name} {request.quantity} {request.symbol} "
            f"(tag {request.tag}) timed out and the order cannot be found - not placing it again"
        )

    # --- working an order ---------------------------------------------------------------------

    def _wait(self, order_id: str, seconds: float) -> OrderState:
        state = self.broker.order(order_id)
        waited = 0.0
        while not state.status.is_final and waited < seconds:
            self.clock.sleep(self.policy.poll_s)
            waited += self.policy.poll_s
            state = self.broker.order(order_id)
        return state

    def settle(self, order_id: str) -> OrderState:
        """Cancel if still working and wait until final: a cancel can race a fill."""
        state = self.broker.order(order_id)
        if not state.status.is_final:
            with contextlib.suppress(OrderRejected):  # it completed meanwhile; the read shows it
                self.broker.cancel(order_id)
            state = self._wait(order_id, self.policy.settle_timeout_s)
        if not state.status.is_final:
            raise ExecutionHalted(f"order {order_id} did not become final after cancelling")
        return state

    def execute(self, symbol: str, side: Side, quantity: int, product: str = "MIS") -> Execution:
        try:
            start = self.broker.quote(symbol).touch(side)
        except OrderRejected as exc:
            return Execution(symbol, side, quantity, 0, 0.0, (), f"no quote: {exc}")
        if start is None:
            return Execution(symbol, side, quantity, 0, 0.0, (), "no price on the other side")
        request = OrderRequest(
            symbol,
            side,
            quantity,
            BrokerOrderType.LIMIT,
            start,
            product=product,
            tag=self.new_tag(),
        )
        try:
            order_id = self.place_once(request)
        except OrderRejected as exc:
            return Execution(symbol, side, quantity, 0, 0.0, (), f"rejected: {exc}")

        reason = ""
        state = self._wait(order_id, self.policy.wait_s)
        for _ in range(self.policy.max_reprices):
            if state.status.is_final:
                break
            touch = self.broker.quote(symbol).touch(side)
            if touch is None:  # nobody on the other side right now: wait, do not chase nothing
                state = self._wait(order_id, self.policy.wait_s)
                continue
            if abs(touch / start - 1.0) * 100.0 > self.policy.max_slippage_pct:
                reason = f"price ran {self.policy.max_slippage_pct}% away"
                break
            with contextlib.suppress(OrderRejected):  # filled or cancelled in between
                self.broker.modify(order_id, touch)
            state = self._wait(order_id, self.policy.wait_s)
        else:
            if not state.status.is_final:
                reason = f"not filled after {self.policy.max_reprices} re-prices"

        state = self.settle(order_id)
        if state.status is OrderStatus.REJECTED:
            reason = f"rejected: {state.message}"
        return Execution(
            symbol,
            side,
            quantity,
            state.filled_quantity,
            state.average_price,
            (order_id,),
            "" if state.filled_quantity == quantity else reason,
        )


def net_quantity(executions: Iterable[Execution]) -> dict[str, int]:
    """Signed filled quantity per symbol over a set of executions."""
    totals: dict[str, int] = {}
    for e in executions:
        totals[e.symbol] = totals.get(e.symbol, 0) + int(e.side) * e.filled
    return totals
