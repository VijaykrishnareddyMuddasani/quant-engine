import pandas as pd
import pytest

from quant_engine.backtest import FillModel
from quant_engine.core import Bar, Order, Side

T0 = pd.Timestamp("2026-01-05 09:16", tz="Asia/Kolkata")


def bar(o: float, h: float, lo: float, c: float) -> Bar:
    return Bar(T0, T0 + pd.Timedelta(minutes=1), o, h, lo, c)


EXACT = FillModel()


def test_market_orders_fill_at_the_open_with_adverse_slippage() -> None:
    model = FillModel(slippage_bps=10)
    b = bar(100, 102, 99, 101)
    assert model.fill_price(Order.market(Side.BUY, 1), b) == pytest.approx(100.1)
    assert model.fill_price(Order.market(Side.SELL, 1), b) == pytest.approx(99.9)


@pytest.mark.parametrize(
    ("side", "trigger", "b", "expected"),
    [
        (Side.BUY, 101, bar(103, 104, 102, 103), 103),  # opened through the trigger: the open
        (Side.BUY, 101, bar(100, 102, 99, 101), 101),  # touched inside the bar: the trigger
        (Side.BUY, 105, bar(100, 102, 99, 101), None),  # never reached
        (Side.SELL, 99, bar(97, 98, 96, 97), 97),
        (Side.SELL, 99, bar(100, 101, 98, 99), 99),
        (Side.SELL, 95, bar(100, 101, 98, 99), None),
    ],
)
def test_stops_gap_and_touch(side: Side, trigger: float, b: Bar, expected: float | None) -> None:
    assert EXACT.fill_price(Order.stop(side, 1, trigger), b) == expected


def test_limits_must_trade_through_by_a_tick() -> None:
    order = Order.limit(Side.BUY, 1, 99.0)
    assert EXACT.fill_price(order, bar(98.5, 100, 98, 99)) == 98.5  # opened better: the open
    assert EXACT.fill_price(order, bar(100, 101, 99.0, 100)) is None  # only touched
    assert EXACT.fill_price(order, bar(100, 101, 98.95, 100)) == 99.0  # one tick through
    lenient = FillModel(limit_needs_trade_through=False)
    assert lenient.fill_price(order, bar(100, 101, 99.0, 100)) == 99.0

    sell = Order.limit(Side.SELL, 1, 101.0)
    assert EXACT.fill_price(sell, bar(100, 101.0, 99, 100)) is None
    assert EXACT.fill_price(sell, bar(100, 101.05, 99, 100)) == 101.0


def test_a_stop_placed_after_a_fill_assumes_the_worst_for_the_rest_of_the_bar() -> None:
    b = bar(100, 101, 97, 100.5)
    stop = Order.stop(Side.SELL, 1, 98.0)
    assert EXACT.stop_after_fill(stop, b, reference=100.0) == 98.0
    assert EXACT.stop_after_fill(Order.stop(Side.SELL, 1, 96.0), b, reference=100.0) is None
    assert EXACT.stop_after_fill(Order.stop(Side.SELL, 1, 100.5), b, reference=100.0) == 100.0
    with pytest.raises(ValueError, match="stop orders"):
        EXACT.stop_after_fill(Order.limit(Side.SELL, 1, 102.0), b, reference=100.0)


def test_invalid_fill_models_are_refused() -> None:
    with pytest.raises(ValueError, match="slippage"):
        FillModel(slippage_bps=-1)
