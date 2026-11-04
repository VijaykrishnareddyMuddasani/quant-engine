"""The supervisor that runs a live book, the Kite candle feed and the qe-live wiring."""

import datetime as dt
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from quant_engine.core import IST, Bar, SimulatedClock
from quant_engine.execution import ExecutionHalted, KiteBroker, SimulatedBroker
from quant_engine.execution.kite import KiteBarFeed
from quant_engine.ops import BookSupervisor, KillSwitch, MemoryNotifier
from quant_engine.ops.live_book import BookConfig, build_book
from quant_engine.strategy import StrategyContext
from support import CALENDAR, MONDAY, SYMBOL, Scripted, buy, live_book, ohlc_bars, until

EXAMPLE = Path(__file__).parents[1] / "examples" / "live_book.toml"
FLAT = [(100.0, 100.5, 99.5, 100.0)] * 6


def supervised(
    tmp_path: Path, strategy: Scripted, bars: pd.DataFrame, **kwargs: Any
) -> tuple[BookSupervisor, SimulatedBroker, SimulatedClock, KillSwitch, MemoryNotifier]:
    runner, broker, clock, _ = live_book(tmp_path, strategy, bars)
    kill, notes = KillSwitch(tmp_path / "control", clock), MemoryNotifier()
    return BookSupervisor("demo", runner, kill, notes, clock, **kwargs), broker, clock, kill, notes


def test_a_quiet_session_runs_to_the_end(tmp_path: Path) -> None:
    bars = ohlc_bars(FLAT)
    supervisor, _, _, _, notes = supervised(tmp_path, Scripted(), bars)
    assert supervisor.run(until(bars)) == "done"
    assert [m for m, _ in notes.messages] == ["demo: started", "demo: session over"]


def test_a_stop_request_closes_the_position(tmp_path: Path) -> None:
    bars = ohlc_bars(FLAT)
    strategy = Scripted(at={0: buy(10), 2: lambda bar, ctx: kill.request("demo", "stop")})
    supervisor, broker, _, kill, _ = supervised(tmp_path, strategy, bars)
    assert supervisor.run(until(bars)) == "stopped"
    assert broker.positions() == {}
    assert strategy.fills[-1].tag == "stop requested"


def test_a_takeover_leaves_the_position_alone(tmp_path: Path) -> None:
    bars = ohlc_bars(FLAT)
    strategy = Scripted(at={0: buy(10), 2: lambda bar, ctx: kill.request("demo", "takeover")})
    supervisor, broker, _, kill, notes = supervised(tmp_path, strategy, bars)
    assert supervisor.run(until(bars)) == "takeover"
    assert broker.positions() == {SYMBOL: 10}
    assert notes.messages[-1] == ("demo: handed over - positions left as they are", True)


def test_a_skipped_day_never_starts(tmp_path: Path) -> None:
    bars = ohlc_bars(FLAT)
    supervisor, broker, _, kill, _ = supervised(tmp_path, Scripted(at={0: buy(1)}), bars)
    kill.request("demo", "skip")
    assert supervisor.run(until(bars)) == "skipped"
    assert broker.placed == []


class BuysThenBreaks(Scripted):
    """Buys on the first bar, then raises on every bar after it."""

    def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        super().on_bar(bar, ctx)
        if len(self.seen) > 1:
            raise RuntimeError("strategy bug")


def test_errors_in_a_row_close_the_book(tmp_path: Path) -> None:
    bars = ohlc_bars(FLAT)
    supervisor, broker, _, _, notes = supervised(
        tmp_path, BuysThenBreaks(at={0: buy(5)}), bars, max_errors=3
    )
    assert supervisor.run(until(bars)) == "errors"
    assert broker.positions() == {}
    assert "3 errors in a row" in notes.messages[-1][0]


def test_a_halt_stops_without_trading(tmp_path: Path) -> None:
    bars = ohlc_bars(FLAT)
    supervisor, broker, _, _, notes = supervised(tmp_path, Scripted(), bars)

    def halt() -> None:
        raise ExecutionHalted("cannot tell what the broker holds")

    supervisor.runner.step = halt  # type: ignore[method-assign]
    assert supervisor.run(until(bars)) == "halted"
    assert "HALTED" in notes.messages[-1][0]
    assert broker.placed == []


# --- the Kite candle feed ---------------------------------------------------------------------


class FakeKite:
    """historical_data returns one-minute candles from 09:15 up to and including ``until``."""

    def __init__(self) -> None:
        self.requests = 0

    def historical_data(
        self, token: int, start: dt.datetime, end: dt.datetime, interval: str
    ) -> list[dict[str, Any]]:
        self.requests += 1
        first = dt.datetime.combine(end.date(), dt.time(9, 15))
        minutes = int((end - first).total_seconds() // 60) + 1
        return [
            {
                "date": (first + dt.timedelta(minutes=m)).replace(tzinfo=IST),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 10,
            }
            for m in range(minutes)
        ]


def test_the_feed_releases_only_finished_bars() -> None:
    clock = SimulatedClock(dt.datetime.combine(MONDAY, dt.time(9, 30, 1), tzinfo=IST))
    kite = FakeKite()
    feed = KiteBarFeed(kite, 256265, CALENDAR, 5, clock, history_days=0, publish_delay_s=2.0)
    one_second_after = feed.bars(pd.Timestamp(clock.now()))
    assert [t.strftime("%H:%M") for t in one_second_after.index] == ["09:15", "09:20"]
    clock.sleep(1.5)  # now 2.5 s past 09:30: the 09:25 bar's last minute is published
    later = feed.bars(pd.Timestamp(clock.now()))
    assert [t.strftime("%H:%M") for t in later.index] == ["09:15", "09:20", "09:25"]
    assert later["complete"].all()


# --- qe-live wiring ---------------------------------------------------------------------------


def test_book_config_and_paper_by_default(tmp_path: Path) -> None:
    config = BookConfig.from_toml(EXAMPLE)
    assert config.name == "demo"
    assert config.state_file.parent == EXAMPLE.parent / "state"
    clock = SimulatedClock(dt.datetime.combine(MONDAY, dt.time(9, 15), tzinfo=IST))
    paper = build_book(config, FakeKite(), clock, MemoryNotifier(), live=False)
    assert isinstance(paper.runner.broker, SimulatedBroker)
    live = build_book(config, FakeKite(), clock, MemoryNotifier(), live=True)
    assert isinstance(live.runner.broker, KiteBroker)


@pytest.mark.parametrize("bad", ["[book]\nname = 'x'\n", "[strategy]\nspec = 'a:B'\n"])
def test_an_incomplete_book_config_is_refused(tmp_path: Path, bad: str) -> None:
    path = tmp_path / "book.toml"
    path.write_text(bad)
    with pytest.raises((KeyError, TypeError)):
        BookConfig.from_toml(path)
