"""Kill switch, rest-day guard, preflight checks, notifications and the Telegram command bot."""

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from quant_engine.core import IST, SimulatedClock
from quant_engine.data import ExchangeCalendar
from quant_engine.ops import (
    BookInfo,
    Check,
    CommandRouter,
    KillSwitch,
    RestDayGuard,
    TelegramBot,
    TelegramError,
    TelegramNotifier,
    TelegramPoller,
    chunks,
    positions_in_state_files,
    report,
    run_checks,
)
from quant_engine.ops import guard as guard_module
from quant_engine.ops.preflight import holiday_list, static_ip

CALENDAR = ExchangeCalendar.nse()
TOKEN = "123456789" + ":" + "x" * 35  # built at run time: the leak guard scans this file


def clock_at(day: dt.date = dt.date(2026, 1, 5), hhmm: str = "08:45") -> SimulatedClock:
    return SimulatedClock(dt.datetime.combine(day, dt.time.fromisoformat(hhmm), tzinfo=IST))


# --- kill switch ------------------------------------------------------------------------------


def test_a_request_counts_only_on_the_day_it_was_made(tmp_path: Path) -> None:
    clock = clock_at()
    kill = KillSwitch(tmp_path, clock)
    kill.request("demo", "stop", "testing")
    assert kill.active("demo")
    clock.advance_to(clock.now() + dt.timedelta(days=1))
    assert not kill.active("demo")
    assert [p.name for p in kill.sweep()] == ["demo.stop"]


def test_an_unreadable_request_counts_as_active(tmp_path: Path) -> None:
    (tmp_path / "demo.stop").write_text("not json")
    assert KillSwitch(tmp_path, clock_at()).active("demo")


def test_book_names_cannot_escape_the_folder(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid book name"):
        KillSwitch(tmp_path, clock_at()).request("../evil")


# --- rest-day guard ---------------------------------------------------------------------------

REPUBLIC_DAY = dt.date(2026, 1, 26)


@pytest.mark.parametrize(
    ("day", "holds", "rest"),
    [
        (dt.date(2026, 1, 5), False, False),  # trading day
        (REPUBLIC_DAY, False, True),  # listed holiday, nothing held
        (REPUBLIC_DAY, True, False),  # a position on a "holiday": the list is wrong, run
        (dt.date(2026, 1, 10), False, True),  # Saturday
        (dt.date(2031, 1, 6), False, False),  # no list for the year: run every weekday
    ],
)
def test_the_guard_rests_only_when_sure(day: dt.date, holds: bool, rest: bool) -> None:
    assert RestDayGuard(CALENDAR, lambda: holds).decide(day).rest is rest


def test_a_failing_position_check_means_run() -> None:
    def broken() -> bool:
        raise OSError("disk unreadable")

    decision = RestDayGuard(CALENDAR, broken).decide(REPUBLIC_DAY)
    assert not decision.rest
    assert "unknown" in decision.reason


def test_guard_exit_codes(tmp_path: Path) -> None:
    state = tmp_path / "demo.json"
    assert guard_module.main(["--date", str(REPUBLIC_DAY), "--state", str(state)]) == 10
    state.write_text(json.dumps({"position": -75}))
    assert guard_module.main(["--date", str(REPUBLIC_DAY), "--state", str(state)]) == 0
    assert positions_in_state_files([state])()


# --- preflight --------------------------------------------------------------------------------


def test_preflight_reports_each_check_and_survives_a_crash() -> None:
    def crash() -> tuple[bool, str]:
        raise RuntimeError("boom")

    results = run_checks(
        [
            static_ip("203.0.113.5", lookup=lambda: "203.0.113.5"),
            static_ip("203.0.113.5", lookup=lambda: "203.0.113.9"),
            Check("crashes", crash),
            holiday_list(CALENDAR, dt.date(2026, 12, 15)),  # next year's list not added yet
        ]
    )
    assert [r.ok for r in results] == [True, False, False, False]
    text = report(results)
    assert "FAIL  crashes: check crashed: RuntimeError: boom" in text
    assert "holiday list for 2027 MISSING" in text


# --- notifications ----------------------------------------------------------------------------


def test_chunks_respect_the_limit_and_keep_lines_whole() -> None:
    text = "\n".join(f"line {i}" for i in range(100))
    parts = chunks(text, limit=50)
    assert all(len(p) <= 50 for p in parts)
    assert "".join(parts) == text
    assert chunks("x" * 120, limit=50) == ["x" * 50, "x" * 50, "x" * 20]


class FakeTelegram:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = replies
        self.sent: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.sent.append((url.rsplit("/", 1)[-1], payload))
        reply = self.replies.pop(0) if self.replies else {"ok": True, "result": True}
        if isinstance(reply, Exception):
            raise reply
        return dict(reply)


def test_telegram_retries_and_never_leaks_the_token() -> None:
    post = FakeTelegram(
        [
            OSError("network down"),
            {"ok": False, "description": f"bad {TOKEN}"},
            {"ok": False, "description": "still bad"},
        ]
    )
    bot = TelegramBot(TOKEN, post=post, clock=clock_at())
    with pytest.raises(TelegramError) as caught:
        bot.call("sendMessage", {"text": "hi"})
    assert TOKEN not in str(caught.value)
    assert len(post.sent) == 3


def test_notifier_sends_quietly_unless_urgent() -> None:
    post = FakeTelegram([])
    TelegramNotifier(TelegramBot(TOKEN, post=post, clock=clock_at()), "42").send("hi", urgent=True)
    assert post.sent == [
        ("sendMessage", {"chat_id": "42", "text": "hi", "disable_notification": False})
    ]


# --- the command bot --------------------------------------------------------------------------


@pytest.fixture
def router(tmp_path: Path) -> CommandRouter:
    books = [BookInfo("alpha", lambda: "flat"), BookInfo("beta", lambda: "position +75")]
    return CommandRouter(books, KillSwitch(tmp_path, clock_at()), clock_at())


def test_stop_and_status(router: CommandRouter) -> None:
    assert router.handle("/stop beta") == "stop requested for beta (today only)"
    assert router.handle("/status") == "alpha: flat\nbeta: position +75 [stop requested]"
    assert "no book called" in router.handle("/stop gamma")
    assert router.handle("/stop") == "stop requested for alpha, beta (today only)"


def test_takeover_needs_a_timely_confirmation(router: CommandRouter) -> None:
    assert router.handle("/confirm") == "nothing to confirm"
    assert "send /confirm within 60 s" in router.handle("/takeover alpha")
    assert router.handle("/confirm") == "alpha handed over: it will stop managing its positions"
    assert router.kill.active("alpha", "takeover")

    router.handle("/takeover beta")
    router.clock.advance_to(router.clock.now() + dt.timedelta(seconds=61))  # type: ignore[attr-defined]
    assert router.handle("/confirm") == "too late: send /takeover again"
    assert not router.kill.active("beta", "takeover")


def test_skip_and_help(router: CommandRouter) -> None:
    assert router.handle("/skip").startswith("no trading today")
    assert router.kill.active("alpha", "skip")
    assert router.handle("/whatever").startswith("/status")


def test_the_poller_obeys_only_its_chat_and_only_fresh_commands(router: CommandRouter) -> None:
    now = int(router.clock.now().timestamp())
    updates = [
        {"update_id": 1, "message": {"chat": {"id": 666}, "date": now, "text": "/stop"}},
        {"update_id": 2, "message": {"chat": {"id": 42}, "date": now - 86_400, "text": "/stop"}},
        {"update_id": 3, "message": {"chat": {"id": 42}, "date": now, "text": "/stop alpha"}},
    ]
    post = FakeTelegram([{"ok": True, "result": updates}])
    poller = TelegramPoller(
        TelegramBot(TOKEN, post=post, clock=router.clock), "42", router, router.clock
    )
    assert poller.poll_once() == 1
    assert poller.offset == 4
    assert router.kill.active("alpha")
    assert not router.kill.active("beta")  # the stranger's and yesterday's /stop were ignored
    assert post.sent[-1] == (
        "sendMessage",
        {"chat_id": "42", "text": "stop requested for alpha (today only)"},
    )
