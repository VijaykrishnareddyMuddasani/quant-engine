"""``qe-live``: run one strategy as a live book for today's session.

Paper by default: orders fill in a simulated broker against real Kite quotes. Real orders need
``--live`` on the command line; no config file setting can switch it on, so a copied config can
never trade money by accident.

    qe-live book.toml            # paper
    qe-live book.toml --live     # real orders

Credentials come from the environment, never from the config file: KITE_API_KEY and
KITE_ACCESS_TOKEN (from the day's manual login), and optionally TELEGRAM_BOT_TOKEN with
TELEGRAM_CHAT_ID for notifications.
"""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quant_engine.core.clock import Clock, SystemClock
from quant_engine.data.calendar import ExchangeCalendar
from quant_engine.execution.broker import Broker
from quant_engine.execution.kite import KiteBarFeed, KiteBroker
from quant_engine.execution.live import LiveConfig, LiveRunner
from quant_engine.execution.orders import OrderExecutor
from quant_engine.execution.simulated import SimulatedBroker
from quant_engine.execution.state import StateStore
from quant_engine.ops.guard import RestDayGuard, positions_in_state_files
from quant_engine.ops.killswitch import KillSwitch
from quant_engine.ops.notify import ConsoleNotifier, Notifier, TelegramBot, TelegramNotifier
from quant_engine.ops.supervisor import BookSupervisor
from quant_engine.strategy.loader import load_strategy


@dataclass(frozen=True)
class BookConfig:
    name: str
    symbol: str
    instrument_token: int
    strategy_spec: str
    strategy_params: Mapping[str, Any] = field(default_factory=dict)
    bar_minutes: int = 5
    history_days: int = 1
    product: str = "MIS"
    backstop_pct: float | None = None
    max_errors: int = 30
    state_dir: Path = Path("state")
    control_dir: Path = Path("control")

    @classmethod
    def from_toml(cls, path: str | Path) -> BookConfig:
        path = Path(path)
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        book, strategy = dict(raw["book"]), dict(raw["strategy"])
        for key in ("state_dir", "control_dir"):
            if key in book:
                book[key] = path.parent / book[key]
        return cls(
            strategy_spec=strategy["spec"], strategy_params=strategy.get("params", {}), **book
        )

    @property
    def state_file(self) -> Path:
        return self.state_dir / f"{self.name}.json"


def build_book(
    config: BookConfig,
    kite: Any,
    clock: Clock,
    notifier: Notifier,
    *,
    live: bool,
    calendar: ExchangeCalendar | None = None,
) -> BookSupervisor:
    """Wire a book together. With ``live=False`` orders go to a simulated broker priced by Kite."""
    calendar = calendar or ExchangeCalendar.nse()
    kite_broker = KiteBroker(kite, clock)
    broker: Broker = kite_broker if live else SimulatedBroker(kite_broker)
    feed = KiteBarFeed(
        kite,
        config.instrument_token,
        calendar,
        config.bar_minutes,
        clock,
        history_days=config.history_days,
    )
    runner = LiveRunner(
        load_strategy(config.strategy_spec, config.strategy_params),
        feed,
        broker,
        OrderExecutor(broker, clock),
        calendar,
        StateStore(config.state_file, clock),
        LiveConfig(config.symbol, config.product, backstop_pct=config.backstop_pct),
        clock,
        notify=lambda text: notifier.send(text, urgent=True),
    )
    return BookSupervisor(
        config.name,
        runner,
        KillSwitch(config.control_dir, clock),
        notifier,
        clock,
        max_errors=config.max_errors,
    )


def _notifier() -> Notifier:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    return TelegramNotifier(TelegramBot(token), chat) if token and chat else ConsoleNotifier()


def _kite() -> Any:  # pragma: no cover - needs the optional kiteconnect package and a session
    from kiteconnect import KiteConnect

    kite = KiteConnect(api_key=os.environ["KITE_API_KEY"])
    kite.set_access_token(os.environ["KITE_ACCESS_TOKEN"])
    return kite


def main(argv: Sequence[str] | None = None, kite_factory: Callable[[], Any] = _kite) -> int:
    parser = argparse.ArgumentParser(prog="qe-live", description="Run a live (or paper) book.")
    parser.add_argument("config", type=Path)
    parser.add_argument("--live", action="store_true", help="send real orders (default: paper)")
    args = parser.parse_args(argv)

    config = BookConfig.from_toml(args.config)
    clock, calendar, notifier = SystemClock(), ExchangeCalendar.nse(), _notifier()
    today = clock.now().date()
    decision = RestDayGuard(calendar, positions_in_state_files([config.state_file])).decide(today)
    if decision.rest:
        print(f"{config.name}: rest day ({decision.reason})")
        return 0
    KillSwitch(config.control_dir, clock).sweep()
    supervisor = build_book(
        config, kite_factory(), clock, notifier, live=args.live, calendar=calendar
    )
    mode = "LIVE" if args.live else "paper"
    notifier.send(f"{config.name}: starting in {mode} mode")
    outcome = supervisor.run(calendar.session_close(today))
    return 0 if outcome in {"done", "skipped", "stopped", "takeover"} else 1


if __name__ == "__main__":
    sys.exit(main())
