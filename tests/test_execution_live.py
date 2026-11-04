import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from quant_engine.core import IST, Fill, Order, Side, SimulatedClock
from quant_engine.execution import ExecutionHalted, OrderStatus, StateError, StateStore, reconcile
from quant_engine.strategy import StrategyContext
from support import CALENDAR, MONDAY, SYMBOL, Scripted, buy, live_book, ohlc_bars, until

RISING = [(100 + i, 100.6 + i, 99.8 + i, 100.5 + i) for i in range(5)]


def test_the_live_runner_trades_the_same_strategy_object(tmp_path: Path) -> None:
    bars = ohlc_bars(RISING)
    strategy = Scripted(at={0: buy(10)})
    runner, broker, _, state = live_book(tmp_path, strategy, bars)
    runner.run_until(until(bars))
    assert [s["start"] for s in strategy.seen] == list(bars.index)
    (fill,) = strategy.fills
    assert (fill.quantity, fill.price) == (10, pytest.approx(100.55))  # bar 0 close + half spread
    assert broker.positions() == {SYMBOL: 10}
    assert state.load()["position"] == 10


def test_a_restart_resumes_and_a_mismatch_refuses_to_start(tmp_path: Path) -> None:
    bars = ohlc_bars(RISING)
    first, broker, _, _ = live_book(tmp_path, Scripted(at={0: buy(10)}), bars)
    first.run_until(until(bars))

    again, _, _, _ = live_book(tmp_path, Scripted(), bars, broker=broker)
    again.start()
    assert again.position == 10

    notes: list[str] = []
    stranger, _, _, _ = live_book(tmp_path, Scripted(), bars)  # a broker that holds nothing
    stranger.notify = notes.append
    with pytest.raises(ExecutionHalted, match="book 10, broker 0"):
        stranger.start()
    assert "not starting" in notes[0]


def test_engine_stops_fire_on_the_bar_that_breaks_them(tmp_path: Path) -> None:
    bars = ohlc_bars(
        [(100, 100.5, 99.8, 100.2), (100.2, 100.4, 99.9, 100.1), (100, 100.1, 97, 97.5)]
    )

    def protect(fill: Fill, ctx: StrategyContext) -> None:
        if ctx.position > 0:
            ctx.submit(Order.stop(Side.SELL, 10, 99.0, tag="stop"))

    strategy = Scripted(at={0: buy(10)}, on_fill_do=protect)
    runner, broker, _, _ = live_book(tmp_path, strategy, bars)
    runner.run_until(until(bars))
    assert [f.tag for f in strategy.fills] == ["", "stop"]
    assert broker.positions() == {}


def test_an_intraday_book_is_flat_at_the_close(tmp_path: Path) -> None:
    close = CALENDAR.session_close(MONDAY)
    start = (close - pd.Timedelta(minutes=3)).strftime("%H:%M")
    bars = ohlc_bars([(100, 101, 99, 100)] * 3, start=start)
    strategy = Scripted(at={0: buy(5)})
    runner, broker, _, _ = live_book(tmp_path, strategy, bars)
    runner.run_until(until(bars))
    assert [f.tag for f in strategy.fills] == ["", "session end"]
    assert broker.positions() == {}


def test_a_broker_side_backstop_covers_the_position_and_is_picked_up(tmp_path: Path) -> None:
    bars = ohlc_bars(
        [
            (100, 100.5, 99.8, 100.2),
            (100.2, 100.3, 100.0, 100.1),
            (99, 99, 96, 96.5),
            (96.5, 97, 96, 96.8),
        ]
    )
    strategy = Scripted(at={0: buy(10)})
    runner, broker, _, state = live_book(tmp_path, strategy, bars, backstop_pct=2.0)
    runner.run_until(until(bars))
    backstop = next(o for o in broker.orders() if o.request.trigger is not None)
    assert backstop.status is OrderStatus.COMPLETE
    assert [f.tag for f in strategy.fills] == ["", "backstop"]
    assert broker.positions() == {}
    assert state.load()["position"] == 0


def test_live_limit_orders_are_refused_not_half_done(tmp_path: Path) -> None:
    bars = ohlc_bars(RISING[:2])
    runner, _, _, _ = live_book(tmp_path, Scripted(), bars)
    with pytest.raises(NotImplementedError, match="LIMIT"):
        runner.submit(Order.limit(Side.BUY, 1, 99.0))


def test_state_store_saves_atomically_and_guards_its_life_cycle(tmp_path: Path) -> None:
    clock = SimulatedClock(dt.datetime(2026, 1, 5, 9, 15, tzinfo=IST))
    store = StateStore(tmp_path / "s.json", clock)
    assert store.load() == {"phase": "IDLE"}
    store.move("ENTERING", position=0)
    assert StateStore(tmp_path / "s.json", clock).load()["phase"] == "ENTERING"
    with pytest.raises(StateError, match="ENTERING to DONE"):
        store.move("DONE")
    assert not list(tmp_path.glob("*.tmp"))


def test_reconcile_ignores_other_books_symbols() -> None:
    result = reconcile({"NFO:A": 10}, {"NFO:A": 10, "NFO:OTHER": -50}, ignore=["NFO:OTHER"])
    assert result.ok
    mismatch = reconcile({"NFO:A": 10}, {"NFO:A": 5})
    assert mismatch.describe() == "NFO:A: book 10, broker 5"
