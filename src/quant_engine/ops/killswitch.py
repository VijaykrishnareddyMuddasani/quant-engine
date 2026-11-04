"""Stop and takeover requests for each book, as small dated files.

A file is the right interface: the Telegram bot, a shell on the server, or a person with a phone
and SSH can all create one, and a book checks it on every poll whatever state it is in.

Each request records the day it was made and **counts only on that day**. An undated stop file
outlives its purpose: left over from last week, it would block today's session, and nobody can
tell an old file from a fresh one by looking. ``sweep`` removes old requests.

A request file that cannot be read counts as active. For a stop, that is the safe direction:
missing a day of trading costs less than ignoring a real stop.
"""

from __future__ import annotations

import json
from pathlib import Path

from quant_engine.core.clock import Clock
from quant_engine.core.storage import atomic_write_json

KINDS = ("stop", "takeover", "skip")


class KillSwitch:
    def __init__(self, folder: str | Path, clock: Clock) -> None:
        self.folder = Path(folder)
        self.clock = clock

    def _path(self, book: str, kind: str) -> Path:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        if not book or any(c in book for c in "/\\.:"):
            raise ValueError(f"invalid book name {book!r}")
        return self.folder / f"{book}.{kind}"

    def request(self, book: str, kind: str = "stop", reason: str = "") -> Path:
        path = self._path(book, kind)
        now = self.clock.now()
        atomic_write_json(
            path, {"date": now.date().isoformat(), "at": now.isoformat(), "reason": reason}
        )
        return path

    def active(self, book: str, kind: str = "stop") -> bool:
        path = self._path(book, kind)
        if not path.exists():
            return False
        try:
            made = json.loads(path.read_text(encoding="utf-8"))["date"]
        except (OSError, ValueError, KeyError, TypeError):
            return True  # unreadable: assume it is meant
        return bool(made == self.clock.now().date().isoformat())

    def clear(self, book: str, kind: str = "stop") -> None:
        self._path(book, kind).unlink(missing_ok=True)

    def sweep(self) -> list[Path]:
        """Delete requests made before today; returns what was removed."""
        today = self.clock.now().date().isoformat()
        removed = []
        for path in self.folder.glob("*.*"):
            if path.suffix.lstrip(".") not in KINDS:
                continue
            try:
                made = json.loads(path.read_text(encoding="utf-8"))["date"]
            except (OSError, ValueError, KeyError, TypeError):
                continue  # unreadable files stay, and keep counting as active
            if made < today:
                path.unlink()
                removed.append(path)
        return removed
