"""Walk-forward analysis and the parameter search it wraps.

Walk-forward answers a narrower question than a sealed hold-out: *does re-fitting on the recent
past choose parameters that keep working on the next stretch?* Each fold fits on a training window
and is scored on the test window that follows it; only the test windows count. Anchored folds keep
every day from the start in training; rolling folds keep a fixed-length window.

``GridSearch`` records every candidate it scores, because the number of trials is part of the
result: the best of 1,000 variants is expected to look good by luck alone (see
``significance.deflated_sharpe_ratio`` and ``significance.luck_test``).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Generic, TypeVar

import pandas as pd

from quant_engine.backtest.metrics import t_statistic
from quant_engine.backtest.results import BacktestResult
from quant_engine.validation.segments import Segment

P = TypeVar("P")


@dataclass(frozen=True)
class Fold:
    number: int
    train: Segment
    test: Segment


def walk_forward_folds(
    days: Sequence[dt.date],
    train_days: int,
    test_days: int,
    *,
    anchored: bool = False,
    step_days: int | None = None,
) -> list[Fold]:
    """Folds over ``days``: train on ``train_days`` (or everything before, if anchored), test on the
    next ``test_days``, then move on by ``step_days`` (default: one test window). Only complete
    test windows are made."""
    if train_days < 1 or test_days < 1:
        raise ValueError("train_days and test_days must be positive")
    step = step_days or test_days
    ordered = sorted(days)
    folds: list[Fold] = []
    first_test = train_days
    while first_test + test_days <= len(ordered):
        number = len(folds) + 1
        train_start = 0 if anchored else first_test - train_days
        folds.append(
            Fold(
                number,
                Segment(f"F{number}-train", ordered[train_start], ordered[first_test - 1]),
                Segment(
                    f"F{number}-test", ordered[first_test], ordered[first_test + test_days - 1]
                ),
            )
        )
        first_test += step
    if not folds:
        raise ValueError(f"{len(ordered)} days are too few for {train_days} + {test_days}")
    return folds


@dataclass
class GridSearch(Generic[P]):
    """Score every candidate with ``score`` and keep the best; remembers all the scores."""

    candidates: Sequence[P]
    score: Callable[[pd.DataFrame, P], float]
    scores: list[tuple[P, float]] = field(default_factory=list)

    def __call__(self, bars: pd.DataFrame) -> P:
        if not self.candidates:
            raise ValueError("no candidates to search")
        trial = [(c, self.score(bars, c)) for c in self.candidates]
        self.scores.extend(trial)
        valid = [(c, s) for c, s in trial if s == s]  # drop NaN scores
        if not valid:
            raise ValueError("every candidate scored NaN")
        return max(valid, key=lambda cs: cs[1])[0]

    @property
    def trials(self) -> int:
        return len(self.scores)


@dataclass(frozen=True)
class FoldResult(Generic[P]):
    fold: Fold
    params: P
    result: BacktestResult


@dataclass(frozen=True)
class WalkForwardReport(Generic[P]):
    folds: list[FoldResult[P]]

    def out_of_sample_trades(self) -> pd.DataFrame:
        """Every test-window trade, stitched together, with the fold it came from."""
        frames = [f.result.trades.assign(fold=f.fold.number) for f in self.folds]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def summary(self) -> pd.DataFrame:
        rows = []
        for f in self.folds:
            net = f.result.trades["net_return_pct"]
            rows.append(
                {
                    "fold": f.fold.number,
                    "test": f"{f.fold.test.start} to {f.fold.test.end}",
                    "params": f.params,
                    "trades": len(net),
                    "avg_net_return_pct": net.mean() if len(net) else float("nan"),
                    "t_stat": t_statistic(net),
                }
            )
        return pd.DataFrame(rows)


def run_walk_forward(
    bars: pd.DataFrame,
    folds: Iterable[Fold],
    fit: Callable[[pd.DataFrame], P],
    test: Callable[[pd.DataFrame, P], BacktestResult],
) -> WalkForwardReport[P]:
    """Per fold: ``fit`` on the training bars, then ``test`` the chosen params on the test bars."""
    results = []
    for fold in folds:
        params = fit(fold.train.select(bars))
        results.append(FoldResult(fold, params, test(fold.test.select(bars), params)))
    return WalkForwardReport(results)
