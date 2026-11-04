"""Keeping one live book running for one session, and stopping it the right way.

Each poll the supervisor checks the kill switch before stepping the book:

* **takeover**: stop managing immediately and leave the positions exactly as they are (a person
  has them now);
* **stop**: close the position and stop;
* **skip** (before the start): do not trade today at all.

Errors are counted in a row. One is reported at once, then every tenth, and ``max_errors`` in a
row close the position and stop the book. ``ExecutionHalted`` is different: it means the book no
longer knows what the broker holds, so it stops *without* trading and asks for a person.
"""

from __future__ import annotations

import pandas as pd

from quant_engine.core.clock import Clock
from quant_engine.execution.live import LiveRunner
from quant_engine.execution.orders import ExecutionHalted
from quant_engine.ops.killswitch import KillSwitch
from quant_engine.ops.notify import Notifier


class BookSupervisor:
    def __init__(
        self,
        name: str,
        runner: LiveRunner,
        kill: KillSwitch,
        notifier: Notifier,
        clock: Clock,
        *,
        poll_s: float = 1.0,
        max_errors: int = 30,
    ) -> None:
        self.name, self.runner, self.kill = name, runner, kill
        self.notifier, self.clock = notifier, clock
        self.poll_s, self.max_errors = poll_s, max_errors

    def run(self, end: pd.Timestamp) -> str:
        """Run until ``end``; returns how the session ended."""
        if self.kill.active(self.name, "skip"):
            self.notifier.send(f"{self.name}: skipping today as requested")
            return "skipped"
        try:
            self.runner.start()
        except ExecutionHalted:
            return "halted"  # the runner has already said why
        self.notifier.send(f"{self.name}: started")

        errors = 0
        while pd.Timestamp(self.clock.now()) < end:
            if self.kill.active(self.name, "takeover"):
                self.notifier.send(
                    f"{self.name}: handed over - positions left as they are", urgent=True
                )
                return "takeover"
            if self.kill.active(self.name, "stop"):
                self.runner.flatten("stop requested")
                self.notifier.send(f"{self.name}: stopped on request, position closed", urgent=True)
                return "stopped"
            try:
                self.runner.step()
                errors = 0
            except ExecutionHalted as exc:
                self.notifier.send(f"{self.name}: HALTED, needs a person - {exc}", urgent=True)
                return "halted"
            except Exception as exc:
                errors += 1
                if errors == 1 or errors % 10 == 0:
                    self.notifier.send(
                        f"{self.name}: error {errors} in a row - {type(exc).__name__}: {exc}",
                        urgent=True,
                    )
                if errors >= self.max_errors:
                    return self._emergency_close()
            self.clock.sleep(self.poll_s)

        self.runner.finish()
        self.notifier.send(f"{self.name}: session over")
        return "done"

    def _emergency_close(self) -> str:
        try:
            self.runner.flatten("too many errors")
            note = "position closed"
        except Exception as exc:
            note = f"CLOSING FAILED ({type(exc).__name__}: {exc}) - close it by hand"
        self.notifier.send(
            f"{self.name}: {self.max_errors} errors in a row, stopping; {note}", urgent=True
        )
        return "errors"
