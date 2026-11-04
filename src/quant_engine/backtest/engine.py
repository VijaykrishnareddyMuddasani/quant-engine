"""The event-driven backtester.

For every bar, in time order:

1. working orders placed *before* this bar are matched against it (``FillModel``), and the
   strategy hears about each fill; protective stops it places in reaction may still trigger in
   the rest of the bar;
2. the strategy sees the completed bar and may place or cancel orders;
3. on the last bar of a session, DAY orders are cancelled and, for intraday books, the position is
   closed at the bar's close;
4. equity is marked at the close.

A position still open after the last bar is closed at the last close and tagged "end of data", so
every result accounts for every unit traded.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_engine.backtest.costs import CostModel, NoCosts
from quant_engine.backtest.fills import PRIORITY, FillModel
from quant_engine.backtest.ledger import Ledger
from quant_engine.backtest.results import BacktestResult, fills_frame, trades_frame
from quant_engine.core.types import Bar, Fill, Order, OrderType, Side, WorkingOrder
from quant_engine.data.schema import OHLC, datetime_index, validate_ohlcv
from quant_engine.strategy.base import Strategy


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 1_000_000.0
    fill_model: FillModel = field(default_factory=FillModel)
    costs: CostModel = field(default_factory=NoCosts)
    flatten_at_session_end: bool = True


@dataclass(frozen=True)
class _Working:
    public: WorkingOrder
    bar_index: int
    reaction_price: float | None  # set when placed inside on_fill: the price that was just filled

    @property
    def order(self) -> Order:
        return self.public.order


def prepare_bars(bars: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Validate ``bars`` and drop blank rows. Returns the bars to run on and the number dropped."""
    if "available_at" not in bars.columns:
        raise ValueError(
            "bars need an available_at column - resample_session(bars, minutes, calendar) adds it"
        )
    validate_ohlcv(bars).raise_if_failed()
    priced = bars[list(OHLC)].notna().all(axis=1)
    frame = bars[priced]
    available = pd.DatetimeIndex(frame["available_at"])
    if bool((available <= datetime_index(frame)).any()):
        raise ValueError("every bar's available_at must be after its start")
    return frame, int((~priced).sum())


class Backtester:
    def __init__(self, strategy: Strategy, config: BacktestConfig | None = None) -> None:
        self.strategy = strategy
        self.config = config or BacktestConfig()

    def run(self, bars: pd.DataFrame) -> BacktestResult:
        return _Run(self.strategy, self.config, bars).execute()


class _Run:
    """The mutable state of one backtest run; also the strategy's context while it runs."""

    def __init__(self, strategy: Strategy, config: BacktestConfig, bars: pd.DataFrame) -> None:
        self.strategy = strategy
        self.config = config
        self.frame, self.skipped = prepare_bars(bars)
        if self.frame.empty:
            raise ValueError("no priced bars to run on")
        index = datetime_index(self.frame)
        days = index.normalize()
        self.session_end = np.r_[np.asarray(days[1:] != days[:-1]), True]
        self.available = pd.DatetimeIndex(self.frame["available_at"])
        self.ledger = Ledger(config.initial_capital)
        self.working: dict[int, _Working] = {}
        self.fills: list[Fill] = []
        self.ids = itertools.count(1)
        self.i = -1
        self.reaction_price: float | None = None

    # --- StrategyContext ----------------------------------------------------------------------

    @property
    def now(self) -> pd.Timestamp:
        return self.available[self.i] if self.i >= 0 else datetime_index(self.frame)[0]

    @property
    def position(self) -> float:
        return self.ledger.position

    @property
    def working_orders(self) -> tuple[WorkingOrder, ...]:
        return tuple(w.public for w in self.working.values())

    @property
    def is_session_end(self) -> bool:
        return self.i >= 0 and bool(self.session_end[self.i])

    def history(self, bars: int | None = None) -> pd.DataFrame:
        if bars is not None and bars <= 0:
            raise ValueError("history needs a positive number of bars")
        stop = self.i + 1
        start = 0 if bars is None else max(0, stop - bars)
        return self.frame.iloc[start:stop]

    def submit(self, order: Order) -> int:
        order_id = next(self.ids)
        public = WorkingOrder(order_id, order, self.now)
        self.working[order_id] = _Working(public, self.i, self.reaction_price)
        return order_id

    def cancel(self, order_id: int) -> None:
        self.working.pop(order_id, None)

    def cancel_all(self) -> None:
        self.working.clear()

    # --- the loop -----------------------------------------------------------------------------

    def execute(self) -> BacktestResult:
        f = self.frame
        o, h, lo, c = (f[col].to_numpy(dtype=float) for col in OHLC)
        v = f["volume"].to_numpy(dtype=float) if "volume" in f.columns else np.zeros(len(f))
        starts = datetime_index(f)
        equity = np.empty(len(f))
        position = np.empty(len(f))

        self.strategy.on_start(self)
        bar = None
        for i in range(len(f)):
            self.i = i
            bar = Bar(starts[i], self.available[i], o[i], h[i], lo[i], c[i], v[i])
            self._match(bar)
            self.strategy.on_bar(bar, self)
            if self.session_end[i]:
                self._end_session(bar)
            equity[i] = self.ledger.equity(bar.close)
            position[i] = self.ledger.position
        if bar is not None and self.ledger.position != 0:
            self._close_position(bar, "end of data")
            equity[-1] = self.ledger.equity(bar.close)
            position[-1] = self.ledger.position
        self.strategy.on_finish(self)

        return BacktestResult(
            strategy=self.strategy.name,
            initial_capital=self.config.initial_capital,
            trades=trades_frame(self.ledger.trades),
            fills=fills_frame(self.fills),
            equity=pd.Series(equity, index=self.available, name="equity"),
            position=pd.Series(position, index=self.available, name="position"),
            skipped_bars=self.skipped,
        )

    def _match(self, bar: Bar) -> None:
        model = self.config.fill_model
        ready = sorted(
            (w for w in self.working.values() if w.bar_index < self.i),
            key=lambda w: (PRIORITY[w.order.type], w.public.id),
        )
        for w in ready:
            if w.public.id in self.working:  # an OCO sibling or the strategy may have cancelled it
                price = model.fill_price(w.order, bar)
                if price is not None:
                    self._execute(w, price, bar.start)

        # Stops placed in reaction to the fills above: the rest of this bar may still hit them.
        reactive = [
            w
            for w in self.working.values()
            if w.bar_index == self.i
            and w.reaction_price is not None
            and w.order.type is OrderType.STOP
        ]
        for w in sorted(reactive, key=lambda w: w.public.id):
            if w.public.id in self.working and w.reaction_price is not None:
                price = model.stop_after_fill(w.order, bar, w.reaction_price)
                if price is not None:
                    self._execute(w, price, bar.start)

    def _execute(self, w: _Working, price: float, when: pd.Timestamp) -> None:
        del self.working[w.public.id]
        if w.order.oco is not None:
            for other in [x for x in self.working.values() if x.order.oco == w.order.oco]:
                del self.working[other.public.id]
        self._book(w.public.id, w.order.side, w.order.quantity, price, when, w.order.tag)

    def _book(
        self, order_id: int, side: Side, quantity: float, price: float, when: pd.Timestamp, tag: str
    ) -> None:
        cost = self.config.costs.cost(side, quantity, price)
        fill = Fill(order_id, when, side, quantity, price, cost, tag)
        self.ledger.apply(fill, self.i)
        self.fills.append(fill)
        with self._reacting_to(fill):
            self.strategy.on_fill(fill, self)

    @contextmanager
    def _reacting_to(self, fill: Fill) -> Iterator[None]:
        self.reaction_price = fill.price
        try:
            yield
        finally:
            self.reaction_price = None

    def _close_position(self, bar: Bar, tag: str) -> None:
        side = Side.of(-self.ledger.position)
        price = self.config.fill_model.adverse(bar.close, side)
        self._book(next(self.ids), side, abs(self.ledger.position), price, bar.available_at, tag)

    def _end_session(self, bar: Bar) -> None:
        flatten = self.config.flatten_at_session_end
        if flatten and self.ledger.position != 0:
            self._close_position(bar, "session end")
        for order_id, w in list(self.working.items()):
            if flatten or not w.order.good_till_cancelled:
                del self.working[order_id]
