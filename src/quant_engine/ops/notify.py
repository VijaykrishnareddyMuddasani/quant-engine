"""Telling a person what the books are doing.

``TelegramNotifier`` talks to the Bot API over plain HTTPS (no SDK). Messages longer than
Telegram's limit are split, sends are retried with backoff, and the bot token never appears in an
error message or a log line: it is part of every request URL, so a careless traceback would leak
it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

from quant_engine.core.clock import Clock, SystemClock

TELEGRAM_LIMIT = 4096


class Notifier(Protocol):
    def send(self, text: str, *, urgent: bool = False) -> None: ...


class ConsoleNotifier:
    def __init__(self, write: Callable[[str], None] = print) -> None:
        self.write = write

    def send(self, text: str, *, urgent: bool = False) -> None:
        self.write(("!! " if urgent else "") + text)


class MemoryNotifier:
    """Keeps messages in a list: tests, and dry runs."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, bool]] = []

    def send(self, text: str, *, urgent: bool = False) -> None:
        self.messages.append((text, urgent))


Post = Callable[[str, dict[str, Any], float], dict[str, Any]]


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url, json.dumps(payload).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result: dict[str, Any] = json.load(response)
        return result


def chunks(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split on line breaks where possible, so no message exceeds ``limit`` characters."""
    parts: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            parts.append(current)
            current = ""
        current += line
    if current or not parts:
        parts.append(current)
    return parts


class TelegramError(RuntimeError):
    """A Telegram call failed; the message never contains the bot token."""


class TelegramBot:
    """The Bot API calls the engine needs, with the token kept out of every error."""

    def __init__(
        self,
        token: str,
        *,
        post: Post = post_json,
        clock: Clock | None = None,
        attempts: int = 3,
        timeout_s: float = 10.0,
    ) -> None:
        self._token = token
        self.post = post
        self.clock = clock or SystemClock()
        self.attempts = attempts
        self.timeout_s = timeout_s

    def call(self, method: str, payload: dict[str, Any], timeout_s: float | None = None) -> Any:
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        last = ""
        for attempt in range(self.attempts):
            try:
                reply = self.post(url, payload, timeout_s or self.timeout_s)
                if reply.get("ok"):
                    return reply.get("result")
                last = str(reply.get("description", "not ok"))
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                last = type(exc).__name__
            if attempt + 1 < self.attempts:
                self.clock.sleep(2.0**attempt)
        raise TelegramError(
            f"{method} failed after {self.attempts} attempts: {last}".replace(
                self._token, "<token>"
            )
        )


class TelegramNotifier:
    def __init__(self, bot: TelegramBot, chat_id: str) -> None:
        self.bot = bot
        self.chat_id = chat_id

    def send(self, text: str, *, urgent: bool = False) -> None:
        for part in chunks(text):
            self.bot.call(
                "sendMessage",
                {"chat_id": self.chat_id, "text": part, "disable_notification": not urgent},
            )
