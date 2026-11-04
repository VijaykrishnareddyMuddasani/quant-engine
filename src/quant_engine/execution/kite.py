"""Zerodha Kite Connect behind the ``Broker`` protocol.

The adapter takes an already-authenticated ``KiteConnect`` object, so this module never sees a
password or an API secret, and imports nothing from ``kiteconnect`` itself. That keeps the
dependency optional and lets the tests drive the adapter with a stand-in.

Kite's failures are mapped onto the three cases the engine distinguishes (see ``broker``):
a network error while *placing* may have reached the exchange, so it is ``OutcomeUnknown``; the
same error on a read is ``BrokerUnavailable``; order and input errors are ``OrderRejected``.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, TypeVar

import pandas as pd

from quant_engine.core.clock import Clock
from quant_engine.core.types import Side
from quant_engine.data.calendar import ExchangeCalendar
from quant_engine.data.resample import resample_session
from quant_engine.execution.broker import (
    BrokerError,
    BrokerOrderType,
    BrokerUnavailable,
    OrderRejected,
    OrderRequest,
    OrderState,
    OrderStatus,
    OutcomeUnknown,
    Quote,
)
from quant_engine.execution.ratelimit import RateLimiter

T = TypeVar("T")

KITE_TAG_LIMIT = 20
_REJECTIONS = {"OrderException", "InputException"}
_NETWORK = {"NetworkException", "Timeout", "ReadTimeout", "ConnectTimeout", "ConnectionError"}
_FINAL_STATUS = {
    "COMPLETE": OrderStatus.COMPLETE,
    "CANCELLED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
    "TRIGGER PENDING": OrderStatus.TRIGGER_PENDING,
}


def _status(text: str) -> OrderStatus:
    # Kite has many transient states (OPEN PENDING, VALIDATION PENDING, MODIFY PENDING ...);
    # anything not final or trigger-pending is still working.
    return _FINAL_STATUS.get(text.upper(), OrderStatus.OPEN)


class KiteBroker:
    def __init__(
        self,
        kite: Any,
        clock: Clock,
        *,
        quote_interval_s: float = 1.0,
        order_interval_s: float = 0.1,
    ) -> None:
        self.kite = kite
        self._quote_limit = RateLimiter(quote_interval_s, clock)
        self._order_limit = RateLimiter(order_interval_s, clock)
        self._requests: dict[str, OrderRequest] = {}

    def _call(self, limiter: RateLimiter, call: Callable[[], T], *, placing: bool = False) -> T:
        limiter.wait()
        try:
            return call()
        except Exception as exc:
            kind = type(exc).__name__
            if kind in _REJECTIONS:
                raise OrderRejected(str(exc)) from exc
            if kind in _NETWORK:
                raise (OutcomeUnknown if placing else BrokerUnavailable)(str(exc)) from exc
            raise BrokerError(f"{kind}: {exc}") from exc

    # --- Broker -------------------------------------------------------------------------------

    def place(self, request: OrderRequest) -> str:
        if len(request.tag) > KITE_TAG_LIMIT:
            raise ValueError(f"Kite tags are at most {KITE_TAG_LIMIT} characters")
        exchange, symbol = request.symbol.split(":", 1)
        params: dict[str, Any] = {
            "variety": "regular",
            "exchange": exchange,
            "tradingsymbol": symbol,
            "transaction_type": "BUY" if request.side is Side.BUY else "SELL",
            "quantity": request.quantity,
            "product": request.product,
            "order_type": request.order_type.value,
            "tag": request.tag or None,
        }
        if request.price is not None:
            params["price"] = request.price
        if request.trigger is not None:
            params["trigger_price"] = request.trigger
        order_id = str(
            self._call(self._order_limit, lambda: self.kite.place_order(**params), placing=True)
        )
        self._requests[order_id] = request
        return order_id

    def modify(self, order_id: str, price: float) -> None:
        self._call(
            self._order_limit,
            lambda: self.kite.modify_order(variety="regular", order_id=order_id, price=price),
        )

    def cancel(self, order_id: str) -> None:
        self._call(
            self._order_limit, lambda: self.kite.cancel_order(variety="regular", order_id=order_id)
        )

    def order(self, order_id: str) -> OrderState:
        history = self._call(self._order_limit, lambda: self.kite.order_history(order_id))
        if not history:
            raise BrokerUnavailable(f"no history yet for order {order_id}")
        return self._state(history[-1])

    def orders(self) -> list[OrderState]:
        return [self._state(row) for row in self._call(self._order_limit, self.kite.orders)]

    def positions(self) -> dict[str, int]:
        net = self._call(self._order_limit, self.kite.positions)["net"]
        return {
            f"{p['exchange']}:{p['tradingsymbol']}": int(p["quantity"])
            for p in net
            if int(p["quantity"]) != 0
        }

    def quote(self, symbol: str) -> Quote:
        data = self._call(self._quote_limit, lambda: self.kite.quote([symbol]))[symbol]
        depth = data.get("depth", {})
        bids, asks = depth.get("buy") or [], depth.get("sell") or []
        bid = bids[0]["price"] if bids and bids[0].get("price") else None
        ask = asks[0]["price"] if asks and asks[0].get("price") else None
        stamp = data.get("timestamp") or data.get("last_trade_time") or dt.datetime.now(dt.UTC)
        return Quote(symbol, bid, ask, float(data["last_price"]), stamp)

    # --- mapping ------------------------------------------------------------------------------

    def _state(self, row: dict[str, Any]) -> OrderState:
        order_id = str(row["order_id"])
        request = self._requests.get(order_id) or OrderRequest(
            symbol=f"{row['exchange']}:{row['tradingsymbol']}",
            side=Side.BUY if row["transaction_type"] == "BUY" else Side.SELL,
            quantity=int(row["quantity"]),
            order_type=BrokerOrderType(row["order_type"]),
            price=row.get("price") or None,
            trigger=row.get("trigger_price") or None,
            product=row.get("product", "MIS"),
            tag=row.get("tag") or "",
        )
        return OrderState(
            order_id=order_id,
            request=request,
            status=_status(str(row["status"])),
            filled_quantity=int(row.get("filled_quantity") or 0),
            average_price=float(row.get("average_price") or 0.0),
            message=str(row.get("status_message") or ""),
        )


class KiteBarFeed:
    """Completed bars built from Kite's minute candles on the session grid.

    A minute candle is used only after it has closed and ``publish_delay_s`` more has passed,
    because Kite publishes (and may still revise) the last minute shortly after it ends. A bar
    with a missing minute is held back until ``final_after_s`` past its end, then released
    incomplete rather than never. Candle requests are spaced ``min_fetch_interval_s`` apart.
    """

    def __init__(
        self,
        kite: Any,
        instrument_token: int,
        calendar: ExchangeCalendar,
        bar_minutes: int,
        clock: Clock,
        *,
        history_days: int = 1,
        publish_delay_s: float = 2.0,
        final_after_s: float = 20.0,
        min_fetch_interval_s: float = 1.0,
    ) -> None:
        self.kite, self.token, self.calendar = kite, instrument_token, calendar
        self.bar_minutes, self.clock, self.history_days = bar_minutes, clock, history_days
        self.publish_delay = pd.Timedelta(seconds=publish_delay_s)
        self.final_after = pd.Timedelta(seconds=final_after_s)
        self._limit = RateLimiter(min_fetch_interval_s, clock)
        self._minutes = pd.DataFrame()

    def _fetch(self, until: pd.Timestamp) -> pd.DataFrame:
        first = until.date()
        for _ in range(self.history_days):
            first = self.calendar.previous_trading_day(first)
        start = self.calendar.session_open(first)
        self._limit.wait()
        try:
            rows = self.kite.historical_data(
                self.token,
                start.tz_localize(None).to_pydatetime(),
                until.tz_convert(self.calendar.tz).tz_localize(None).to_pydatetime(),
                "minute",
            )
        except Exception as exc:
            kind = type(exc).__name__
            raise BrokerUnavailable(f"minute candles unavailable ({kind}: {exc})") from exc
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        frame = pd.DataFrame(rows)
        stamps = pd.DatetimeIndex(pd.to_datetime(frame.pop("date")))
        stamps = stamps.tz_localize(self.calendar.tz) if stamps.tz is None else stamps
        return frame.set_axis(stamps.tz_convert(self.calendar.tz))[
            ["open", "high", "low", "close", "volume"]
        ]

    def bars(self, until: pd.Timestamp) -> pd.DataFrame:
        minutes = self._fetch(until)
        starts = pd.DatetimeIndex(minutes.index)
        published = starts + (pd.Timedelta(minutes=1) + self.publish_delay) <= until
        closed = minutes[published & self.calendar.is_open_mask(starts)]
        bars = resample_session(closed, self.bar_minutes, self.calendar)
        if bars.empty:
            return bars
        ended = pd.DatetimeIndex(bars["available_at"]) + self.publish_delay <= until
        final = bars["complete"].to_numpy() | (
            pd.DatetimeIndex(bars["available_at"]) + self.final_after <= until
        )
        return bars[ended & final]
