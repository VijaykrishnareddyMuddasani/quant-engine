import datetime as dt

import pytest

from quant_engine.core import IST, Side, SimulatedClock
from quant_engine.execution import (
    ChasePolicy,
    ExecutionHalted,
    Fault,
    Leg,
    MultiLegExecutor,
    OrderExecutor,
    OrderState,
    OrderStatus,
    Quote,
    SimulatedBroker,
    StaticQuotes,
)

FUT, CALL, PUT = "NFO:FUT", "NFO:CALL", "NFO:PUT"
FAST = ChasePolicy(wait_s=1.0, poll_s=0.5, max_reprices=3, max_slippage_pct=1.0)


def setup(**broker_kwargs: int) -> tuple[SimulatedClock, StaticQuotes, SimulatedBroker]:
    clock = SimulatedClock(dt.datetime(2026, 1, 5, 9, 20, tzinfo=IST))
    quotes = StaticQuotes(clock)
    for symbol in (FUT, CALL, PUT):
        quotes.set(symbol, bid=99.0, ask=100.0)
    return clock, quotes, SimulatedBroker(quotes, **broker_kwargs)


def test_a_marketable_order_fills_at_the_touch() -> None:
    clock, _, broker = setup()
    result = OrderExecutor(broker, clock, FAST).execute(FUT, Side.BUY, 10)
    assert (result.filled, result.average_price, result.complete) == (10, 100.0, True)
    assert broker.positions() == {FUT: 10}


def test_an_unfilled_order_is_repriced_then_cancelled_and_reported() -> None:
    clock, _, broker = setup()
    broker.fills_enabled = False
    result = OrderExecutor(broker, clock, FAST).execute(FUT, Side.SELL, 5)
    assert result.filled == 0
    assert result.reason == "not filled after 3 re-prices"
    assert broker.order(result.order_ids[0]).status is OrderStatus.CANCELLED


def test_chasing_stops_when_the_price_runs_away() -> None:
    clock, quotes, broker = setup()
    broker.fills_enabled = False
    executor = OrderExecutor(broker, clock, FAST)
    original_sleep = clock.sleep

    def market_runs(seconds: float) -> None:
        original_sleep(seconds)
        quotes.set(FUT, bid=101.5, ask=102.0)  # 2% above where the order started

    clock.sleep = market_runs  # type: ignore[method-assign]
    result = executor.execute(FUT, Side.BUY, 5)
    assert result.reason == "price ran 1.0% away"


def test_a_timed_out_placement_is_found_not_repeated() -> None:
    clock, _, broker = setup()
    broker.inject(Fault.TIMEOUT_AFTER_ACCEPT)
    result = OrderExecutor(broker, clock, FAST).execute(FUT, Side.BUY, 10)
    assert len(broker.placed) == 1
    assert result.filled == 10
    assert broker.positions() == {FUT: 10}


def test_a_lost_placement_that_cannot_be_found_halts() -> None:
    clock, _, broker = setup()

    class LosesReplies(SimulatedBroker):
        def orders(self) -> list[OrderState]:
            return []  # the broker never shows the order

    lossy = LosesReplies(broker.quotes)
    lossy.inject(Fault.TIMEOUT_AFTER_ACCEPT)
    with pytest.raises(ExecutionHalted, match="not placing it again"):
        OrderExecutor(lossy, clock, FAST).execute(FUT, Side.BUY, 10)
    assert len(lossy.placed) == 1


def test_an_outage_is_retried_because_nothing_happened() -> None:
    clock, _, broker = setup()
    broker.inject(Fault.UNAVAILABLE, Fault.UNAVAILABLE)
    result = OrderExecutor(broker, clock, FAST).execute(FUT, Side.BUY, 1)
    assert result.complete
    assert len(broker.placed) == 1


def test_a_rejection_is_reported() -> None:
    clock, _, broker = setup()
    broker.inject(Fault.REJECT)
    result = OrderExecutor(broker, clock, FAST).execute(FUT, Side.BUY, 1)
    assert result.filled == 0
    assert result.reason.startswith("rejected")


def test_a_partial_fill_is_reported_as_partial() -> None:
    clock = SimulatedClock(dt.datetime(2026, 1, 5, 9, 20, tzinfo=IST))
    calls = {"n": 0}

    class SellersVanish:
        def quote(self, symbol: str) -> Quote:
            calls["n"] += 1
            ask = 100.0 if calls["n"] <= 2 else None  # sellers leave after the first fill
            return Quote(symbol, 99.0, ask, 99.5, clock.now())

    broker = SimulatedBroker(SellersVanish(), fill_limit=4)
    result = OrderExecutor(broker, clock, FAST).execute(FUT, Side.BUY, 10)
    assert (result.filled, result.complete) == (4, False)
    assert broker.positions() == {FUT: 4}


def test_protective_legs_go_first() -> None:
    clock, _, broker = setup()
    legs = [Leg(CALL, Side.SELL, 2), Leg(PUT, Side.BUY, 2, protective=True)]
    result = MultiLegExecutor(OrderExecutor(broker, clock, FAST)).execute(legs)
    assert result.complete
    assert [e.symbol for e in result.executions] == [PUT, CALL]


def test_a_failed_required_leg_rolls_back_the_filled_ones() -> None:
    clock, _, broker = setup()
    legs = [
        Leg(PUT, Side.BUY, 2, protective=True),
        Leg(CALL, Side.SELL, 2),
        Leg("NFO:NO_QUOTE", Side.SELL, 2),
    ]
    result = MultiLegExecutor(OrderExecutor(broker, clock, FAST)).execute(legs)
    assert not result.complete
    assert "NO_QUOTE" in result.reason
    assert [(r.symbol, r.side) for r in result.rollbacks] == [(CALL, Side.BUY), (PUT, Side.SELL)]
    assert result.balanced
    assert broker.positions() == {}


def test_an_optional_leg_may_fail_alone() -> None:
    clock, _, broker = setup()
    legs = [
        Leg(CALL, Side.SELL, 1),
        Leg("NFO:NO_QUOTE", Side.BUY, 1, protective=True, required=False),
    ]
    result = MultiLegExecutor(OrderExecutor(broker, clock, FAST)).execute(legs)
    assert result.complete
    assert broker.positions() == {CALL: -1}
