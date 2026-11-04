"""May the books rest today?

Starting a book on a holiday costs a few unneeded messages. *Not* starting it on a trading day
can leave an open position without its stops. So the guard answers "rest" only when it is sure:

* the day is a weekend, or a holiday written in the calendar's list, **and**
* no book reports an open position, and the position check itself worked.

A position on a "holiday" means the list is wrong (the exchange's own contract calendar says that
day trades), so the book runs. A year with no holiday list runs every weekday.

``qe-guard`` exits with code 10 for a rest day and 0 otherwise, so a shell script can decide
without parsing text; any crash exits with another code, and the script runs the book.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from quant_engine.core.storage import read_json
from quant_engine.data.calendar import ExchangeCalendar

REST_EXIT_CODE = 10


@dataclass(frozen=True)
class GuardDecision:
    rest: bool
    reason: str


class RestDayGuard:
    def __init__(self, calendar: ExchangeCalendar, holds_position: Callable[[], bool]) -> None:
        self.calendar = calendar
        self.holds_position = holds_position

    def decide(self, day: dt.date) -> GuardDecision:
        if self.calendar.is_trading_day(day):
            if not self.calendar.covers(day):
                return GuardDecision(False, f"no holiday list for {day.year}: assuming it trades")
            return GuardDecision(False, "trading day")
        why = self.calendar.holiday_name(day) or "weekend"
        try:
            holding = self.holds_position()
        except Exception as exc:  # any failure to know means: run
            return GuardDecision(False, f"{why}, but positions are unknown ({exc}): running")
        if holding:
            return GuardDecision(False, f"{why}, but a position is open: running")
        return GuardDecision(True, why)


def positions_in_state_files(paths: Sequence[Path]) -> Callable[[], bool]:
    """A position check over book state files; an unreadable file raises (and so means run)."""

    def check() -> bool:
        for path in paths:
            state = read_json(path, default={}) or {}
            if int(state.get("position", 0)) != 0:
                return True
        return False

    return check


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qe-guard", description="Exit 10 on a rest day.")
    parser.add_argument("--date", type=dt.date.fromisoformat, default=dt.date.today())
    parser.add_argument(
        "--state",
        type=Path,
        nargs="*",
        default=[],
        help="book state files to check for open positions",
    )
    args = parser.parse_args(argv)
    guard = RestDayGuard(ExchangeCalendar.nse(), positions_in_state_files(args.state))
    decision = guard.decide(args.date)
    print(f"{args.date}: {'rest' if decision.rest else 'run'} - {decision.reason}")
    return REST_EXIT_CODE if decision.rest else 0


if __name__ == "__main__":
    sys.exit(main())
