import pandas as pd
import pytest

from quant_engine.core import Order, OrderType, Side, Trade


def test_side_helpers() -> None:
    assert Side.of(3) is Side.BUY
    assert Side.of(-0.5) is Side.SELL
    assert Side.BUY.opposite is Side.SELL
    with pytest.raises(ValueError, match="zero"):
        Side.of(0)


def test_order_constructors() -> None:
    stop = Order.stop(Side.SELL, 2, 99.5, oco="bracket")
    assert (stop.type, stop.price, stop.oco) == (OrderType.STOP, 99.5, "bracket")
    assert Order.market(Side.BUY, 1).price is None
    assert Order.limit(Side.BUY, 1, 101.0, good_till_cancelled=True).good_till_cancelled


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: Order.market(Side.BUY, 0), "positive"),
        (lambda: Order.market(Side.BUY, float("nan")), "positive"),
        (lambda: Order(Side.BUY, 1, OrderType.MARKET, 100.0), "no price"),
        (lambda: Order(Side.BUY, 1, OrderType.LIMIT), "needs a positive price"),
        (lambda: Order.stop(Side.BUY, 1, -5.0), "needs a positive price"),
    ],
)
def test_invalid_orders_are_refused(make: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        make()  # type: ignore[operator]


def test_trade_returns_are_in_percent_of_entry_notional() -> None:
    t = Trade(
        direction=-1,
        quantity=10,
        entry_time=pd.Timestamp("2026-01-05 09:16", tz="UTC"),
        exit_time=pd.Timestamp("2026-01-05 09:20", tz="UTC"),
        entry_price=200.0,
        exit_price=190.0,
        gross_pnl=100.0,
        costs=20.0,
        bars_held=4,
    )
    assert t.net_pnl == 80.0
    assert t.gross_return_pct == pytest.approx(5.0)
    assert t.net_return_pct == pytest.approx(4.0)
