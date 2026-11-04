"""Persisted book state and the reconciliation that checks it against the broker.

A live book writes its state after every transition, atomically, so a restart (a crash, a server
reboot, a new deployment mid-trade) resumes from what actually happened. Before acting on that
state, it reconciles it with the broker's positions. A disagreement is never "fixed" by guessing:
the book halts and says what differs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quant_engine.core.clock import Clock
from quant_engine.core.storage import atomic_write_json, read_json

# A small book life cycle: which phase may follow which.
BOOK_PHASES: dict[str, set[str]] = {
    "IDLE": {"ENTERING", "DONE"},
    "ENTERING": {"IN_TRADE", "IDLE"},
    "IN_TRADE": {"EXITING"},
    "EXITING": {"IDLE", "DONE", "IN_TRADE"},
    "DONE": set(),
}


class StateError(RuntimeError):
    """An impossible state transition."""


class StateStore:
    """One JSON document per book, saved atomically after every change."""

    def __init__(
        self,
        path: str | Path,
        clock: Clock,
        transitions: Mapping[str, set[str]] | None = None,
        initial_phase: str = "IDLE",
    ) -> None:
        self.path = Path(path)
        self.clock = clock
        self.transitions = dict(transitions or BOOK_PHASES)
        self.initial_phase = initial_phase

    def load(self) -> dict[str, Any]:
        state = read_json(self.path, default=None)
        return dict(state) if state else {"phase": self.initial_phase}

    def update(self, **changes: Any) -> dict[str, Any]:
        state = self.load()
        state.update(changes, updated_at=self.clock.now().isoformat())
        atomic_write_json(self.path, state)
        return state

    def move(self, phase: str, **changes: Any) -> dict[str, Any]:
        """Change phase, refusing transitions the life cycle does not allow."""
        current = self.load()["phase"]
        if phase not in self.transitions.get(current, set()):
            raise StateError(f"cannot move from {current} to {phase}")
        return self.update(phase=phase, **changes)


@dataclass(frozen=True)
class Reconciliation:
    differences: dict[str, tuple[int, int]] = field(default_factory=dict)  # symbol: (ours, broker)

    @property
    def ok(self) -> bool:
        return not self.differences

    def describe(self) -> str:
        if self.ok:
            return "positions agree with the broker"
        return "; ".join(
            f"{symbol}: book {ours}, broker {theirs}"
            for symbol, (ours, theirs) in sorted(self.differences.items())
        )


def reconcile(
    expected: Mapping[str, int], broker: Mapping[str, int], *, ignore: Iterable[str] = ()
) -> Reconciliation:
    """Compare the book's expected positions with the broker's.

    ``ignore`` lists symbols owned by other books trading in the same account, so their positions
    are not mistaken for this book's.
    """
    skip = set(ignore)
    symbols = (set(expected) | set(broker)) - skip
    differences = {
        s: (int(expected.get(s, 0)), int(broker.get(s, 0)))
        for s in symbols
        if int(expected.get(s, 0)) != int(broker.get(s, 0))
    }
    return Reconciliation(differences)
