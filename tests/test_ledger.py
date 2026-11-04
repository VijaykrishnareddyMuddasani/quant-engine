import pandas as pd
import pytest

from quant_engine.backtest import Ledger
from quant_engine.core import Fill, Side

T = pd.Timestamp("2026-01-05 09:15", tz="Asia/Kolkata")


def fill(side: Side, qty: float, price: float, cost: float = 0.0, tag: str = "") -> Fill:
    return Fill(0, T, side, qty, price, cost, tag)


def test_a_long_round_trip() -> None:
    ledger = Ledger(10_000)
    ledger.apply(fill(Side.BUY, 10, 100.0, cost=5, tag="in"), 0)
    assert ledger.equity(103.0) == pytest.approx(10_000 - 5 + 30)
    ledger.apply(fill(Side.SELL, 10, 104.0, cost=5, tag="out"), 3)
    (trade,) = ledger.trades
    assert (trade.direction, trade.quantity, trade.bars_held) == (1, 10, 3)
    assert (trade.gross_pnl, trade.costs, trade.net_pnl) == (40.0, 10.0, 30.0)
    assert (trade.entry_tag, trade.exit_tag) == ("in", "out")
    assert ledger.position == 0
    assert ledger.cash == pytest.approx(10_030)


def test_a_short_round_trip() -> None:
    ledger = Ledger(0)
    ledger.apply(fill(Side.SELL, 5, 200.0), 0)
    ledger.apply(fill(Side.BUY, 5, 190.0), 1)
    assert ledger.trades[0].direction == -1
    assert ledger.trades[0].gross_pnl == 50.0


def test_adds_and_partial_exits_make_one_trade_at_average_prices() -> None:
    ledger = Ledger(0)
    ledger.apply(fill(Side.BUY, 10, 100.0), 0)
    ledger.apply(fill(Side.BUY, 10, 110.0), 1)
    ledger.apply(fill(Side.SELL, 5, 120.0), 2)
    assert ledger.trades == []
    ledger.apply(fill(Side.SELL, 15, 100.0), 4)
    (trade,) = ledger.trades
    assert trade.quantity == 20
    assert trade.entry_price == pytest.approx(105.0)
    assert trade.exit_price == pytest.approx(105.0)
    assert trade.gross_pnl == pytest.approx(0.0)


def test_a_reversal_closes_one_trade_and_opens_the_next_splitting_the_charge() -> None:
    ledger = Ledger(0)
    ledger.apply(fill(Side.BUY, 10, 100.0), 0)
    ledger.apply(fill(Side.SELL, 30, 101.0, cost=30.0), 1)  # 10 close the long, 20 open a short
    assert ledger.position == -20
    assert ledger.trades[0].costs == pytest.approx(10.0)
    ledger.apply(fill(Side.BUY, 20, 99.0), 2)
    short = ledger.trades[1]
    assert (short.direction, short.quantity) == (-1, 20)
    assert short.costs == pytest.approx(20.0)
    assert short.gross_pnl == pytest.approx(40.0)
