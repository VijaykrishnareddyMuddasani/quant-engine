"""Backtest runs described in a TOML file, so a run is data you can keep, diff and re-run.

.. code-block:: toml

    [data]
    path = "bars.csv"            # one-minute bars, any layout read_bars understands...
    # synthetic = { start = 2026-01-01, end = 2026-03-31, seed = 7 }   # ...or a synthetic market
    bar_minutes = 15

    [strategy]
    spec = "package.module:ClassName"
    params = { fast = 8, slow = 21 }

    [backtest]
    initial_capital = 1_000_000
    flatten_at_session_end = true
    slippage_bps = 1.0
    tick = 0.05
    costs = { bps = 2.0 }        # or { schedule = "zerodha_index_options_2026" }; omit for none

Unknown keys are errors: a typo must not silently fall back to a default.
"""

from __future__ import annotations

import datetime as dt
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from quant_engine.backtest.costs import SCHEDULES, BpsCost, CostModel, NoCosts
from quant_engine.backtest.engine import BacktestConfig, Backtester
from quant_engine.backtest.fills import FillModel
from quant_engine.backtest.results import BacktestResult
from quant_engine.data.calendar import ExchangeCalendar
from quant_engine.data.io import read_bars
from quant_engine.data.resample import resample_session
from quant_engine.data.synthetic import SyntheticMarket
from quant_engine.strategy.loader import load_strategy


class ConfigError(ValueError):
    """The run configuration is incomplete or contains unknown keys."""


def _section(raw: Mapping[str, Any], name: str, allowed: set[str]) -> dict[str, Any]:
    section = raw.get(name, {})
    if not isinstance(section, Mapping):
        raise ConfigError(f"[{name}] must be a table")
    unknown = set(section) - allowed
    if unknown:
        raise ConfigError(f"[{name}] has unknown key(s): {', '.join(sorted(unknown))}")
    return dict(section)


def _as_date(value: Any, key: str) -> dt.date:
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise ConfigError(f"synthetic.{key} must be a date, got {value!r}") from exc


def _costs(raw: Any) -> CostModel:
    if raw is None:
        return NoCosts()
    if not isinstance(raw, Mapping) or len(raw) != 1:
        raise ConfigError("costs must be { bps = ... } or { schedule = ... }")
    if "bps" in raw:
        return BpsCost(float(raw["bps"]))
    if "schedule" in raw:
        name = str(raw["schedule"])
        if name not in SCHEDULES:
            raise ConfigError(f"unknown cost schedule {name!r}; known: {', '.join(SCHEDULES)}")
        return SCHEDULES[name]
    raise ConfigError("costs must be { bps = ... } or { schedule = ... }")


@dataclass(frozen=True)
class DataSpec:
    path: Path | None = None
    synthetic: Mapping[str, Any] | None = None
    bar_minutes: int = 1

    def load(self, calendar: ExchangeCalendar) -> pd.DataFrame:
        """One-minute bars from the file or the synthetic market, resampled to ``bar_minutes``."""
        if (self.path is None) == (self.synthetic is None):
            raise ConfigError("[data] needs exactly one of path or synthetic")
        if self.path is not None:
            minutes = read_bars(self.path, tz=calendar.tz)
        else:
            spec = dict(self.synthetic or {})
            unknown = set(spec) - {"start", "end", "seed"}
            if unknown or not {"start", "end"} <= set(spec):
                raise ConfigError("synthetic takes start, end and an optional seed")
            market = SyntheticMarket(calendar, seed=spec.get("seed"))
            minutes = market.minute_bars(
                _as_date(spec["start"], "start"), _as_date(spec["end"], "end")
            )
        return resample_session(minutes, self.bar_minutes, calendar)


@dataclass(frozen=True)
class RunConfig:
    data: DataSpec
    strategy_spec: str
    strategy_params: Mapping[str, Any] = field(default_factory=dict)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)

    @classmethod
    def from_toml(cls, path: str | Path) -> RunConfig:
        path = Path(path)
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        return cls.from_mapping(raw, base_dir=path.parent)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], base_dir: Path = Path()) -> RunConfig:
        unknown = set(raw) - {"data", "strategy", "backtest"}
        if unknown:
            raise ConfigError(f"unknown section(s): {', '.join(sorted(unknown))}")
        data = _section(raw, "data", {"path", "synthetic", "bar_minutes"})
        strategy = _section(raw, "strategy", {"spec", "params"})
        backtest = _section(
            raw,
            "backtest",
            {"initial_capital", "flatten_at_session_end", "slippage_bps", "tick", "costs"},
        )
        if "spec" not in strategy:
            raise ConfigError("[strategy] needs a spec such as 'package.module:ClassName'")

        path = data.get("path")
        return cls(
            data=DataSpec(
                path=(base_dir / path) if path is not None else None,
                synthetic=data.get("synthetic"),
                bar_minutes=int(data.get("bar_minutes", 1)),
            ),
            strategy_spec=str(strategy["spec"]),
            strategy_params=dict(strategy.get("params", {})),
            backtest=BacktestConfig(
                initial_capital=float(backtest.get("initial_capital", 1_000_000.0)),
                fill_model=FillModel(
                    slippage_bps=float(backtest.get("slippage_bps", 0.0)),
                    tick=float(backtest.get("tick", 0.05)),
                ),
                costs=_costs(backtest.get("costs")),
                flatten_at_session_end=bool(backtest.get("flatten_at_session_end", True)),
            ),
        )

    def run(self, calendar: ExchangeCalendar | None = None) -> BacktestResult:
        calendar = calendar or ExchangeCalendar.nse()
        bars = self.data.load(calendar)
        strategy = load_strategy(self.strategy_spec, self.strategy_params)
        return Backtester(strategy, self.backtest).run(bars)
