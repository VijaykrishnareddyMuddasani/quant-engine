"""Telegram control of the books.

``CommandRouter`` turns a command into a reply and, through the kill switch, into an effect. It
holds no network code, so every command is unit-tested. ``TelegramPoller`` is the thin I/O loop
around it. Two safety rules live in the poller:

* only the configured chat is obeyed; anyone else who finds the bot is ignored;
* a command older than ``max_age_s`` is dropped. After a restart Telegram re-delivers anything not
  yet acknowledged, and yesterday's ``/stop`` must not stop today's session.

Commands: ``/status``, ``/stop [book|all]``, ``/skip`` (no trading today), ``/takeover <book>``
then ``/confirm`` within a minute (hand a book's positions to manual control), ``/preflight``.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quant_engine.core.clock import Clock, SystemClock
from quant_engine.core.storage import read_json
from quant_engine.ops.killswitch import KillSwitch
from quant_engine.ops.notify import TelegramBot, TelegramError

HELP = (
    "/status - every book\n"
    "/stop [book|all] - close and stop for today\n"
    "/skip - no trading today\n"
    "/takeover <book> - hand a book to manual control (asks to confirm)\n"
    "/preflight - run the pre-session checks"
)
CONFIRM_WINDOW = dt.timedelta(seconds=60)


@dataclass(frozen=True)
class BookInfo:
    name: str
    status: Callable[[], str]


def state_file_status(path: Path) -> Callable[[], str]:
    """A status line read from a book's state file."""

    def status() -> str:
        state = read_json(path, default=None)
        if not state:
            return "not started today"
        position = int(state.get("position", 0))
        held = f"position {position:+d}" if position else "flat"
        return f"{held}, updated {state.get('updated_at', '?')}"

    return status


class CommandRouter:
    def __init__(
        self,
        books: Sequence[BookInfo],
        kill: KillSwitch,
        clock: Clock,
        preflight: Callable[[], str] | None = None,
    ) -> None:
        self.books = {b.name: b for b in books}
        self.kill = kill
        self.clock = clock
        self.preflight = preflight
        self._pending: tuple[str, dt.datetime] | None = None

    def handle(self, text: str) -> str:
        words = text.strip().split()
        if not words:
            return HELP
        command, args = words[0].lower().split("@")[0], words[1:]
        handlers: dict[str, Callable[[list[str]], str]] = {
            "/status": self._status,
            "/stop": self._stop,
            "/skip": self._skip,
            "/takeover": self._takeover,
            "/confirm": self._confirm,
            "/preflight": self._preflight,
        }
        handler = handlers.get(command)
        return handler(args) if handler is not None else HELP

    def _chosen(self, args: list[str]) -> list[str] | str:
        if not args or args[0].lower() == "all":
            return list(self.books)
        if args[0] not in self.books:
            return f"no book called {args[0]!r}; books: {', '.join(self.books)}"
        return [args[0]]

    def _status(self, args: list[str]) -> str:
        lines = []
        for name, book in self.books.items():
            flags = [kind for kind in ("stop", "skip", "takeover") if self.kill.active(name, kind)]
            note = f" [{', '.join(flags)} requested]" if flags else ""
            try:
                status = book.status()
            except Exception as exc:
                status = f"status unavailable ({type(exc).__name__})"
            lines.append(f"{name}: {status}{note}")
        return "\n".join(lines) or "no books configured"

    def _stop(self, args: list[str]) -> str:
        chosen = self._chosen(args)
        if isinstance(chosen, str):
            return chosen
        for name in chosen:
            self.kill.request(name, "stop", "telegram /stop")
        return f"stop requested for {', '.join(chosen)} (today only)"

    def _skip(self, args: list[str]) -> str:
        for name in self.books:
            self.kill.request(name, "skip", "telegram /skip")
        return "no trading today: every book will stay idle"

    def _takeover(self, args: list[str]) -> str:
        if len(args) != 1 or args[0] not in self.books:
            return f"usage: /takeover <book>; books: {', '.join(self.books)}"
        self._pending = (args[0], self.clock.now() + CONFIRM_WINDOW)
        return (
            f"send /confirm within {CONFIRM_WINDOW.seconds} s to hand {args[0]} to manual "
            "control; its positions will be left exactly as they are"
        )

    def _confirm(self, args: list[str]) -> str:
        pending, self._pending = self._pending, None
        if pending is None:
            return "nothing to confirm"
        book, deadline = pending
        if self.clock.now() > deadline:
            return "too late: send /takeover again"
        self.kill.request(book, "takeover", "telegram /takeover")
        return f"{book} handed over: it will stop managing its positions"

    def _preflight(self, args: list[str]) -> str:
        return self.preflight() if self.preflight else "no preflight checks configured"


class TelegramPoller:
    def __init__(
        self,
        bot: TelegramBot,
        chat_id: str,
        router: CommandRouter,
        clock: Clock,
        *,
        max_age_s: float = 300.0,
        long_poll_s: int = 30,
    ) -> None:
        self.bot, self.chat_id, self.router, self.clock = bot, chat_id, router, clock
        self.max_age = dt.timedelta(seconds=max_age_s)
        self.long_poll_s = long_poll_s
        self.offset: int | None = None

    def poll_once(self) -> int:
        """Fetch new messages, answer the valid ones; returns how many were answered."""
        payload: dict[str, Any] = {"timeout": self.long_poll_s}
        if self.offset is not None:
            payload["offset"] = self.offset
        updates = self.bot.call("getUpdates", payload, timeout_s=self.long_poll_s + 10) or []
        answered = 0
        for update in updates:
            self.offset = int(update["update_id"]) + 1
            message = update.get("message") or {}
            if str(message.get("chat", {}).get("id")) != self.chat_id:
                continue
            sent = dt.datetime.fromtimestamp(int(message.get("date", 0)), dt.UTC)
            if self.clock.now() - sent > self.max_age:
                continue
            reply = self.router.handle(str(message.get("text", "")))
            self.bot.call("sendMessage", {"chat_id": self.chat_id, "text": reply})
            answered += 1
        return answered

    def run_forever(self) -> None:
        while True:
            try:
                self.poll_once()
            except TelegramError as exc:
                print(f"telegram: {exc}", file=sys.stderr)
                self.clock.sleep(5.0)


def main() -> int:
    """Run the bot. Configuration comes from the environment:

    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, QE_CONTROL_DIR (kill-switch folder) and QE_BOOKS, a
    comma-separated list of ``name=path/to/state.json``.
    """
    clock = SystemClock()
    books = [
        BookInfo(name, state_file_status(Path(path)))
        for name, _, path in (item.partition("=") for item in os.environ["QE_BOOKS"].split(","))
    ]
    router = CommandRouter(books, KillSwitch(os.environ["QE_CONTROL_DIR"], clock), clock)
    bot = TelegramBot(os.environ["TELEGRAM_BOT_TOKEN"], clock=clock)
    TelegramPoller(bot, os.environ["TELEGRAM_CHAT_ID"], router, clock).run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
