"""The live ``StrategyContext``: the same ``Strategy`` object the backtester runs, driven by a
clock, a bar feed and a broker.

Per poll (``step``): pick up bars that have completed since the last poll and, for each in order,
check the engine-held stops against it, hand it to the strategy, and execute what the strategy
asked for. Between bars, stops are checked against the live quote. At the session end, DAY orders
lapse and an intraday book is closed.

What is deliberately different from the backtest:

* MARKET orders are worked by ``OrderExecutor`` (a chased limit at the touch), so a fill can be
  partial; the strategy hears exactly what was filled.
* STOP orders are held by the engine and fire as soon as the price is through them. Optionally a
  broker-side stop sits ``backstop_pct`` beyond every position, so the position stays protected
  if this process dies; if that backstop ever fills, the book picks the fill up on the next poll.
* LIMIT orders are not supported live yet and are refused rather than half-implemented.
* Charges are not estimated live (fills carry zero cost); they come from the contract note.

On start the book reconciles its saved position with the broker and refuses to run if they differ.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from quant_engine.core.clock import Clock
from quant_engine.core.types import Bar, Fill, Order, OrderType, Side, WorkingOrder
from quant_engine.data.calendar import ExchangeCalendar
from quant_engine.data.schema import datetime_index
from quant_engine.execution.broker import (
    Broker,
    BrokerOrderType,
    OrderRequest,
    OrderStatus,
    Quote,
)
from quant_engine.execution.orders import ExecutionHalted, OrderExecutor
from quant_engine.execution.state import StateStore, reconcile
from quant_engine.strategy.base import Strategy

Notify = Callable[[str], None]


class BarFeed(Protocol):
    def bars(self, until: pd.Timestamp) -> pd.DataFrame:
        """Completed bars (with ``available_at``) that were knowable at ``until``."""
        ...


class ReplayFeed:
    """Prepared bars released as their ``available_at`` passes: paper rehearsals and tests."""

    def __init__(self, bars: pd.DataFrame) -> None:
        if "available_at" not in bars.columns:
            raise ValueError("ReplayFeed needs bars with an available_at column")
        self._bars = bars

    def bars(self, until: pd.Timestamp) -> pd.DataFrame:
        return self._bars[pd.DatetimeIndex(self._bars["available_at"]) <= until]


class BarQuotes:
    """Quotes made from the last completed bar's close, a half-spread either side."""

    def __init__(self, feed: ReplayFeed, clock: Clock, symbol: str, half_spread: float) -> None:
        self.feed, self.clock, self.symbol, self.half_spread = feed, clock, symbol, half_spread

    def quote(self, symbol: str) -> Quote:
        done = self.feed.bars(pd.Timestamp(self.clock.now()))
        last = float(done["close"].iloc[-1]) if len(done) else float("nan")
        return Quote(
            symbol, last - self.half_spread, last + self.half_spread, last, self.clock.now()
        )


@dataclass(frozen=True)
class LiveConfig:
    symbol: str
    product: str = "MIS"
    poll_s: float = 1.0
    flatten_at_session_end: bool = True
    backstop_pct: float | None = None


class LiveRunner:
    def __init__(
        self,
        strategy: Strategy,
        feed: BarFeed,
        broker: Broker,
        executor: OrderExecutor,
        calendar: ExchangeCalendar,
        state: StateStore,
        config: LiveConfig,
        clock: Clock,
        notify: Notify | None = None,
    ) -> None:
        self.strategy, self.feed, self.broker, self.executor = strategy, feed, broker, executor
        self.calendar, self.state, self.config, self.clock = calendar, state, config, clock
        self.notify = notify or (lambda text: None)
        saved = state.load()
        self._position = int(saved.get("position", 0))
        last = saved.get("last_bar")
        self._last_bar = pd.Timestamp(last) if last else None
        self._backstop_id: str | None = saved.get("backstop_order_id")
        self._history = pd.DataFrame()
        self._bar: Bar | None = None
        self._working: dict[int, WorkingOrder] = {}
        self._pending: list[WorkingOrder] = []
        self._ids = itertools.count(1)
        self._started = False

    # --- StrategyContext ----------------------------------------------------------------------

    @property
    def now(self) -> pd.Timestamp:
        return pd.Timestamp(self.clock.now())

    @property
    def position(self) -> float:
        return float(self._position)

    @property
    def working_orders(self) -> tuple[WorkingOrder, ...]:
        return tuple(self._working.values())

    @property
    def is_session_end(self) -> bool:
        bar = self._bar
        return bar is not None and bar.available_at >= self.calendar.session_close(bar.start)

    def history(self, bars: int | None = None) -> pd.DataFrame:
        if bars is not None and bars <= 0:
            raise ValueError("history needs a positive number of bars")
        return self._history if bars is None else self._history.iloc[-bars:]

    def submit(self, order: Order) -> int:
        if order.type is OrderType.LIMIT:
            raise NotImplementedError("live LIMIT orders are not supported yet; use MARKET or STOP")
        working = WorkingOrder(next(self._ids), order, self.now)
        if order.type is OrderType.MARKET:
            self._pending.append(working)
        else:
            self._working[working.id] = working
        return working.id

    def cancel(self, order_id: int) -> None:
        self._working.pop(order_id, None)
        self._pending = [w for w in self._pending if w.id != order_id]

    def cancel_all(self) -> None:
        self._working.clear()
        self._pending.clear()

    # --- running ------------------------------------------------------------------------------

    def start(self) -> None:
        """Reconcile with the broker, then let the strategy prepare. Refuses on any mismatch."""
        held = self.broker.positions().get(self.config.symbol, 0)
        check = reconcile({self.config.symbol: self._position}, {self.config.symbol: held})
        if not check.ok:
            message = f"{self.strategy.name}: not starting - {check.describe()}"
            self.notify(message)
            raise ExecutionHalted(message)
        self.strategy.on_start(self)
        self._started = True

    def step(self) -> None:
        if not self._started:
            raise RuntimeError("call start() before step()")
        self._collect_backstop()
        done = self.feed.bars(self.now)
        new = done if self._last_bar is None else done[datetime_index(done) > self._last_bar]
        available = pd.DatetimeIndex(new["available_at"])
        has_volume = "volume" in new.columns
        for i, start in enumerate(datetime_index(new)):
            self._history = done[datetime_index(done) <= start]
            self._bar = Bar(
                start,
                available[i],
                float(new["open"].iloc[i]),
                float(new["high"].iloc[i]),
                float(new["low"].iloc[i]),
                float(new["close"].iloc[i]),
                float(new["volume"].iloc[i]) if has_volume else 0.0,
            )
            self._trigger_stops(self._bar.low, self._bar.high)
            self.strategy.on_bar(self._bar, self)
            self._execute_pending()
            if self.is_session_end:
                self._end_session()
            self._last_bar = start
            self.state.update(last_bar=start.isoformat())
        if self._working:
            last = self.broker.quote(self.config.symbol).last
            self._trigger_stops(last, last)

    def run_until(self, end: pd.Timestamp) -> None:
        if not self._started:
            self.start()
        while self.now < end:
            self.step()
            self.clock.sleep(self.config.poll_s)
        self.finish()

    def flatten(self, tag: str) -> None:
        """Cancel everything and close the position now (a stop request, an emergency)."""
        self.cancel_all()
        if self._position:
            close = Order.market(Side.of(-self._position), abs(self._position), tag=tag)
            self._fill(WorkingOrder(next(self._ids), close, self.now))

    def finish(self) -> None:
        self.strategy.on_finish(self)

    # --- internals ----------------------------------------------------------------------------

    def _trigger_stops(self, low: float, high: float) -> None:
        for w in sorted(self._working.values(), key=lambda w: w.id):
            if w.id not in self._working or w.order.price is None:
                continue
            hit = high >= w.order.price if w.order.side is Side.BUY else low <= w.order.price
            if hit:
                del self._working[w.id]
                self._fill(w)
        self._execute_pending()  # anything the strategy sent in reaction to a stop

    def _execute_pending(self) -> None:
        while self._pending:
            self._fill(self._pending.pop(0))

    def _fill(self, w: WorkingOrder) -> None:
        if w.order.oco is not None:
            for other in [x for x in self._working.values() if x.order.oco == w.order.oco]:
                del self._working[other.id]
        execution = self.executor.execute(
            self.config.symbol, w.order.side, int(w.order.quantity), self.config.product
        )
        if execution.filled < w.order.quantity:
            self.notify(
                f"{self.strategy.name}: {w.order.side.name} {w.order.quantity} filled "
                f"{execution.filled} ({execution.reason})"
            )
        if execution.filled:
            self._book(
                Fill(
                    w.id,
                    self.now,
                    w.order.side,
                    execution.filled,
                    execution.average_price,
                    0.0,
                    w.order.tag,
                )
            )

    def _book(self, fill: Fill) -> None:
        self._position += int(fill.signed_quantity)
        backstop_fill = self._refresh_backstop(fill.price)
        self.state.update(position=self._position)
        self.strategy.on_fill(fill, self)
        if backstop_fill is not None:
            self.strategy.on_fill(backstop_fill, self)

    def _end_session(self) -> None:
        if self.config.flatten_at_session_end:
            self.flatten("session end")
        for order_id, w in list(self._working.items()):
            if not w.order.good_till_cancelled:
                del self._working[order_id]

    # --- the broker-side backstop -------------------------------------------------------------

    def _refresh_backstop(self, reference: float) -> Fill | None:
        """Replace the broker-side stop to cover the new position.

        The old stop may have filled in the moment before it was cancelled; if so, that fill is
        booked here and returned so the strategy hears about it too.
        """
        pct = self.config.backstop_pct
        if pct is None:
            return None
        backstop_fill = None
        if self._backstop_id is not None:
            old = self.executor.settle(self._backstop_id)
            self._backstop_id = None
            if old.filled_quantity:
                backstop_fill = Fill(
                    next(self._ids),
                    self.now,
                    old.request.side,
                    old.filled_quantity,
                    old.average_price,
                    0.0,
                    "backstop",
                )
                self._position += int(backstop_fill.signed_quantity)
                reference = old.average_price
                self.notify(
                    f"{self.strategy.name}: broker-side backstop filled at "
                    f"{old.average_price} while being replaced"
                )
        if self._position:
            side = Side.of(-self._position)
            trigger = round(reference * (1.0 - side * pct / 100.0), 2)
            request = OrderRequest(
                self.config.symbol,
                side,
                abs(self._position),
                BrokerOrderType.STOP_MARKET,
                trigger=trigger,
                product=self.config.product,
                tag=self.executor.new_tag(),
            )
            self._backstop_id = self.executor.place_once(request)
        self.state.update(backstop_order_id=self._backstop_id)
        return backstop_fill

    def _collect_backstop(self) -> None:
        """If the broker-side backstop filled, book it as the strategy's exit."""
        if self._backstop_id is None:
            return
        state = self.broker.order(self._backstop_id)
        if state.status is not OrderStatus.COMPLETE:
            return
        self._backstop_id = None
        self.cancel_all()
        self.notify(f"{self.strategy.name}: broker-side backstop filled at {state.average_price}")
        self._book(
            Fill(
                next(self._ids),
                self.now,
                state.request.side,
                state.filled_quantity,
                state.average_price,
                0.0,
                "backstop",
            )
        )
        self._execute_pending()
