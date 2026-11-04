"""The research protocol as code: segments, sealed hold-outs, walk-forward, Monte Carlo and
significance tests."""

from quant_engine.validation.montecarlo import MonteCarloReport, bootstrap_indices, resample_trades
from quant_engine.validation.registry import HoldoutRegistry, PassBar, RegistryError, Verdict
from quant_engine.validation.segments import (
    Segment,
    chronological_segments,
    draw_segments,
    trading_days_of,
)
from quant_engine.validation.significance import (
    LuckTestResult,
    bootstrap_ci,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    holm_adjust,
    luck_test,
    probabilistic_sharpe_ratio,
    sign_flip_p_value,
)
from quant_engine.validation.walkforward import (
    Fold,
    GridSearch,
    WalkForwardReport,
    run_walk_forward,
    walk_forward_folds,
)

__all__ = [
    "Fold",
    "GridSearch",
    "HoldoutRegistry",
    "LuckTestResult",
    "MonteCarloReport",
    "PassBar",
    "RegistryError",
    "Segment",
    "Verdict",
    "WalkForwardReport",
    "bootstrap_ci",
    "bootstrap_indices",
    "chronological_segments",
    "deflated_sharpe_ratio",
    "draw_segments",
    "expected_max_sharpe",
    "holm_adjust",
    "luck_test",
    "probabilistic_sharpe_ratio",
    "resample_trades",
    "run_walk_forward",
    "sign_flip_p_value",
    "trading_days_of",
    "walk_forward_folds",
]
