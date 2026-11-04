"""Pre-registration of sealed hold-out tests, and the record of which segments are spent.

The most common way a backtest lies is not a bug. It is a researcher who looks at the hold-out,
changes the rule, and looks again, until the hold-out is just more training data. The registry
makes that impossible to do by accident:

1. **Register** before looking: the idea family, the hypothesis, the segments to open, the exact
   parameters, a SHA-256 hash of every file the run uses, and the pass bar.
2. **Open** once: the run is refused if any hashed file has changed since registration, or if the
   registration was already opened. Opening marks its segments *spent* for the whole family, so a
   tweaked variant cannot be registered on them again.
3. **Record** the result: it is judged against the pass bar written down in step 1.

Everything is kept in one JSON file, written atomically, that can be committed next to the code.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from quant_engine.backtest.metrics import t_statistic
from quant_engine.core.clock import Clock, SystemClock
from quant_engine.core.storage import atomic_write_json, read_json


class RegistryError(RuntimeError):
    """A registration, opening or result that the protocol does not allow."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Verdict:
    passed: bool
    trades: int
    mean: float
    t_stat: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PassBar:
    """What a sealed run must reach, fixed before it runs: enough trades, a mean per-trade net
    return above ``min_mean`` (in %), and a t-statistic of at least ``min_t``."""

    min_trades: int = 30
    min_mean: float = 0.0
    min_t: float = 2.0

    def judge(self, values: Sequence[float]) -> Verdict:
        x = np.asarray(values, dtype=float)
        mean = float(x.mean()) if len(x) else float("nan")
        t = t_statistic(x)
        reasons = []
        if len(x) < self.min_trades:
            reasons.append(f"{len(x)} trades < {self.min_trades}")
        if not mean > self.min_mean:
            reasons.append(f"mean {mean:.4f} <= {self.min_mean}")
        if not t >= self.min_t:
            reasons.append(f"t {t:.2f} < {self.min_t}")
        return Verdict(not reasons, len(x), mean, t, tuple(reasons))


class HoldoutRegistry:
    def __init__(self, path: str | Path, clock: Clock | None = None) -> None:
        self.path = Path(path)
        self.clock = clock or SystemClock()

    # --- storage ------------------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        data = read_json(self.path, default={"registrations": {}, "spent": {}})
        if not isinstance(data, dict):
            raise RegistryError(f"{self.path} is not a registry file")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        atomic_write_json(self.path, data)

    # --- protocol -----------------------------------------------------------------------------

    def spent(self, family: str) -> set[str]:
        return set(self._load()["spent"].get(family, []))

    def register(
        self,
        family: str,
        hypothesis: str,
        segments: Sequence[str],
        files: Sequence[str | Path],
        params: Mapping[str, Any],
        pass_bar: PassBar,
        root: str | Path = ".",
    ) -> str:
        """Write the plan down; returns the registration id."""
        if not segments:
            raise RegistryError("a registration needs at least one sealed segment")
        data = self._load()
        reused = set(segments) & set(data["spent"].get(family, []))
        if reused:
            raise RegistryError(
                f"segment(s) {', '.join(sorted(reused))} already spent for family {family!r}"
            )
        root = Path(root)
        hashes = {Path(f).as_posix(): sha256_file(root / f) for f in files}
        params_json = json.dumps(dict(params), sort_keys=True, default=str)
        fingerprint = hashlib.sha256(
            (params_json + json.dumps(hashes, sort_keys=True)).encode()
        ).hexdigest()
        reg_id = f"{family}-{fingerprint[:10]}"
        if reg_id in data["registrations"]:
            raise RegistryError(f"{reg_id} is already registered")
        data["registrations"][reg_id] = {
            "family": family,
            "hypothesis": hypothesis,
            "segments": list(segments),
            "files": hashes,
            "params": json.loads(params_json),
            "pass_bar": asdict(pass_bar),
            "registered_at": self.clock.now().isoformat(),
            "opened_at": None,
            "verdict": None,
        }
        self._save(data)
        return reg_id

    def changed_files(self, reg_id: str, root: str | Path = ".") -> list[str]:
        entry = self._entry(self._load(), reg_id)
        root = Path(root)
        return [
            name
            for name, digest in entry["files"].items()
            if not (root / name).is_file() or sha256_file(root / name) != digest
        ]

    def open(self, reg_id: str, root: str | Path = ".") -> dict[str, Any]:
        """Unseal the registration's segments, once, if nothing it hashed has changed."""
        data = self._load()
        entry = self._entry(data, reg_id)
        if entry["opened_at"] is not None:
            raise RegistryError(f"{reg_id} was already opened at {entry['opened_at']}")
        changed = self.changed_files(reg_id, root)
        if changed:
            raise RegistryError(f"{reg_id}: changed since registration: {', '.join(changed)}")
        entry["opened_at"] = self.clock.now().isoformat()
        family_spent = set(data["spent"].get(entry["family"], [])) | set(entry["segments"])
        data["spent"][entry["family"]] = sorted(family_spent)
        self._save(data)
        return dict(entry)

    def record_result(self, reg_id: str, net_returns_pct: Sequence[float]) -> Verdict:
        """Judge the sealed run's per-trade net returns against the registered pass bar."""
        data = self._load()
        entry = self._entry(data, reg_id)
        if entry["opened_at"] is None:
            raise RegistryError(f"{reg_id} has not been opened")
        if entry["verdict"] is not None:
            raise RegistryError(f"{reg_id} already has a result")
        verdict = PassBar(**entry["pass_bar"]).judge(net_returns_pct)
        entry["verdict"] = asdict(verdict)
        self._save(data)
        return verdict

    def entries(self) -> dict[str, dict[str, Any]]:
        return dict(self._load()["registrations"])

    @staticmethod
    def _entry(data: dict[str, Any], reg_id: str) -> dict[str, Any]:
        try:
            entry: dict[str, Any] = data["registrations"][reg_id]
        except KeyError:
            raise RegistryError(f"no registration {reg_id!r}") from None
        return entry
