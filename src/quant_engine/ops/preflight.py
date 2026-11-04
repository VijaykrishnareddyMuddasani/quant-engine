"""Checks run before the session, so problems surface at breakfast and not at the first signal.

Each check is small and independent; a check that crashes is reported as failed with its error,
never allowed to take the others down with it.
"""

from __future__ import annotations

import datetime as dt
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from quant_engine.data.calendar import ExchangeCalendar
from quant_engine.execution.broker import Broker


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class Check:
    name: str
    probe: Callable[[], tuple[bool, str]]

    def run(self) -> CheckResult:
        try:
            ok, detail = self.probe()
        except Exception as exc:
            return CheckResult(self.name, False, f"check crashed: {type(exc).__name__}: {exc}")
        return CheckResult(self.name, ok, detail)


def run_checks(checks: Iterable[Check]) -> list[CheckResult]:
    return [check.run() for check in checks]


def report(results: Iterable[CheckResult]) -> str:
    lines = [f"{'PASS' if r.ok else 'FAIL'}  {r.name}: {r.detail}" for r in results]
    return "\n".join(lines)


def public_ipv4(timeout_s: float = 5.0) -> str:
    with urllib.request.urlopen("https://api.ipify.org", timeout=timeout_s) as response:
        return str(response.read().decode().strip())


# --- the standard checks ----------------------------------------------------------------------


def broker_session(broker: Broker) -> Check:
    """The access token works: an authenticated read succeeds."""
    return Check("broker session", lambda: (True, f"{len(broker.positions())} open position(s)"))


def static_ip(registered: str, lookup: Callable[[], str] = public_ipv4) -> Check:
    """API orders must come from the IP address registered with the broker (an exchange rule)."""

    def probe() -> tuple[bool, str]:
        seen = lookup()
        return (
            seen == registered,
            f"public address {'matches' if seen == registered else 'DIFFERS'}",
        )

    return Check("static IP", probe)


def funds(available: Callable[[], float], minimum: float) -> Check:
    def probe() -> tuple[bool, str]:
        cash = available()
        return cash >= minimum, f"{cash:,.0f} available, {minimum:,.0f} needed"

    return Check("funds", probe)


def holiday_list(calendar: ExchangeCalendar, today: dt.date) -> Check:
    """Next year's list is published in December; this fails until it has been added."""

    def probe() -> tuple[bool, str]:
        year = today.year + (1 if today.month == 12 else 0)
        known = calendar.covers(dt.date(year, 1, 1))
        return known, f"holiday list for {year} {'present' if known else 'MISSING'}"

    return Check("holiday list", probe)


def rule_drift(name: str, expected: object, observe: Callable[[], object]) -> Check:
    """An exchange rule the code assumes (a lot size, a tick, an expiry weekday) still holds."""

    def probe() -> tuple[bool, str]:
        seen = observe()
        return seen == expected, f"expected {expected!r}, exchange says {seen!r}"

    return Check(f"rule: {name}", probe)
