"""The Kite adapter, driven by a stand-in for KiteConnect (no network, no kiteconnect import)."""

import datetime as dt
from typing import Any

import pytest

from quant_engine.core import IST, Side, SimulatedClock
from quant_engine.execution import (
    BrokerError,
    BrokerOrderType,
    BrokerUnavailable,
    KiteBroker,
    OrderRejected,
    OrderRequest,
    OrderStatus,
    OutcomeUnknown,
)


class NetworkException(Exception):
    pass


class OrderException(Exception):
    pass


class FakeKite:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_with: Exception | None = None

    def _record(self, name: str, **kwargs: Any) -> None:
        self.calls.append((name, kwargs))
        if self.fail_with is not None:
            raise self.fail_with

    def place_order(self, **kwargs: Any) -> str:
        self._record("place_order", **kwargs)
        return "250105000123"

    def modify_order(self, **kwargs: Any) -> None:
        self._record("modify_order", **kwargs)

    def cancel_order(self, **kwargs: Any) -> None:
        self._record("cancel_order", **kwargs)

    def order_history(self, order_id: str) -> list[dict[str, Any]]:
        self._record("order_history", order_id=order_id)
        row = {
            "order_id": order_id,
            "exchange": "NFO",
            "tradingsymbol": "NIFTYFUT",
            "transaction_type": "SELL",
            "quantity": 75,
            "order_type": "LIMIT",
            "price": 101.5,
            "product": "MIS",
            "tag": "qe091500001",
            "filled_quantity": 75,
            "average_price": 101.5,
            "status_message": None,
        }
        return [{**row, "status": "OPEN PENDING"}, {**row, "status": "COMPLETE"}]

    def orders(self) -> list[dict[str, Any]]:
        self._record("orders")
        return [h | {"order_id": "1"} for h in self.order_history("1")[-1:]]

    def positions(self) -> dict[str, list[dict[str, Any]]]:
        self._record("positions")
        return {
            "net": [
                {"exchange": "NFO", "tradingsymbol": "NIFTYFUT", "quantity": -75},
                {"exchange": "NFO", "tradingsymbol": "OLD", "quantity": 0},
            ]
        }

    def quote(self, keys: list[str]) -> dict[str, Any]:
        self._record("quote", keys=keys)
        return {
            keys[0]: {
                "last_price": 101.0,
                "timestamp": dt.datetime(2026, 1, 5, 9, 20),
                "depth": {"buy": [{"price": 100.95}], "sell": [{"price": 101.05}]},
            }
        }


@pytest.fixture
def setup() -> tuple[FakeKite, KiteBroker, SimulatedClock]:
    clock = SimulatedClock(dt.datetime(2026, 1, 5, 9, 20, tzinfo=IST))
    kite = FakeKite()
    return kite, KiteBroker(kite, clock), clock


def test_place_maps_the_request(setup: tuple[FakeKite, KiteBroker, SimulatedClock]) -> None:
    kite, broker, _ = setup
    request = OrderRequest(
        "NFO:NIFTYFUT", Side.SELL, 75, BrokerOrderType.LIMIT, 101.5, tag="qe091500001"
    )
    assert broker.place(request) == "250105000123"
    name, params = kite.calls[-1]
    assert name == "place_order"
    assert params == {
        "variety": "regular",
        "exchange": "NFO",
        "tradingsymbol": "NIFTYFUT",
        "transaction_type": "SELL",
        "quantity": 75,
        "product": "MIS",
        "order_type": "LIMIT",
        "tag": "qe091500001",
        "price": 101.5,
    }


def test_failures_map_to_the_three_cases(
    setup: tuple[FakeKite, KiteBroker, SimulatedClock],
) -> None:
    kite, broker, _ = setup
    request = OrderRequest("NFO:X", Side.BUY, 1, BrokerOrderType.MARKET)
    kite.fail_with = NetworkException("read timed out")
    with pytest.raises(OutcomeUnknown):
        broker.place(request)  # it may have reached the exchange
    with pytest.raises(BrokerUnavailable):
        broker.orders()  # a read that failed changed nothing
    kite.fail_with = OrderException("insufficient funds")
    with pytest.raises(OrderRejected):
        broker.place(request)
    kite.fail_with = KeyError("surprise")
    with pytest.raises(BrokerError, match="KeyError"):
        broker.positions()


def test_reads_are_mapped(setup: tuple[FakeKite, KiteBroker, SimulatedClock]) -> None:
    _, broker, _ = setup
    state = broker.order("9")
    assert (state.status, state.filled_quantity, state.average_price) == (
        OrderStatus.COMPLETE,
        75,
        101.5,
    )
    assert state.request.tag == "qe091500001"
    assert broker.positions() == {"NFO:NIFTYFUT": -75}
    quote = broker.quote("NFO:NIFTYFUT")
    assert (quote.bid, quote.ask, quote.last) == (100.95, 101.05, 101.0)


def test_tags_longer_than_kite_allows_are_refused(
    setup: tuple[FakeKite, KiteBroker, SimulatedClock],
) -> None:
    _, broker, _ = setup
    with pytest.raises(ValueError, match="20 characters"):
        broker.place(OrderRequest("NFO:X", Side.BUY, 1, BrokerOrderType.MARKET, tag="t" * 21))


def test_quote_requests_are_spaced_one_second_apart(
    setup: tuple[FakeKite, KiteBroker, SimulatedClock],
) -> None:
    _, broker, clock = setup
    start = clock.now()
    broker.quote("NFO:A")
    broker.quote("NFO:A")
    broker.quote("NFO:A")
    assert clock.now() - start == dt.timedelta(seconds=2)
