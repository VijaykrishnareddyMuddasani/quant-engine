"""Is the edge real, or the best of many coin tosses?

* ``bootstrap_ci`` and ``sign_flip_p_value``: uncertainty of one result, without assuming normal
  returns.
* ``probabilistic_sharpe_ratio`` / ``deflated_sharpe_ratio`` (Bailey and Lopez de Prado, 2012 and
  2014): the chance a Sharpe ratio beats a benchmark given the sample's length, skew and fat
  tails, with the benchmark raised to what the best of ``n_trials`` useless strategies would show.
* ``luck_test``: the direct version. Rerun the *whole search* on data with the edge destroyed, many
  times, and see how often noise produces a best result as good as the real one.
* ``holm_adjust``: p-values for a family of tests, controlling the chance of any false positive.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
EULER_GAMMA = 0.5772156649015329
_NORMAL = NormalDist()


def _array(values: Sequence[float]) -> FloatArray:
    x = np.asarray(values, dtype=float)
    if x.size < 2:
        raise ValueError("need at least two observations")
    return x


def bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[FloatArray], float] = np.mean,
    *,
    confidence: float = 0.95,
    n_resamples: int = 10_000,
    seed: int | None = None,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for ``statistic`` of ``values``."""
    x = _array(values)
    rng = np.random.default_rng(seed)
    samples = x[rng.integers(0, x.size, size=(n_resamples, x.size))]
    stats = np.apply_along_axis(statistic, 1, samples)
    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(stats, [tail, 1.0 - tail])
    return float(low), float(high)


def sign_flip_p_value(
    values: Sequence[float], *, n_resamples: int = 10_000, seed: int | None = None
) -> float:
    """One-sided p-value that the mean is above zero, by random sign flips.

    Under the null of no edge (and a distribution symmetric about zero), each trade was as likely to
    have had the opposite sign. The p-value is the share of sign-flipped samples whose mean is at
    least the observed one.
    """
    x = _array(values)
    rng = np.random.default_rng(seed)
    signs = rng.choice((-1.0, 1.0), size=(n_resamples, x.size))
    null_means = (signs * x).mean(axis=1)
    return float((1 + np.sum(null_means >= x.mean())) / (n_resamples + 1))


def _moments(x: FloatArray) -> tuple[float, float, float]:
    mean, sd = float(x.mean()), float(x.std(ddof=1))
    if sd == 0:
        raise ValueError("returns have zero variance")
    z = (x - mean) / x.std(ddof=0)
    return mean / sd, float(np.mean(z**3)), float(np.mean(z**4))


def probabilistic_sharpe_ratio(returns: Sequence[float], benchmark: float = 0.0) -> float:
    """P(true per-period Sharpe > ``benchmark``), allowing for skew and kurtosis of ``returns``."""
    x = _array(returns)
    sharpe, skew, kurtosis = _moments(x)
    spread = 1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2
    z = (sharpe - benchmark) * math.sqrt(x.size - 1) / math.sqrt(spread)
    return _NORMAL.cdf(z)


def expected_max_sharpe(n_trials: int, sharpe_variance: float) -> float:
    """The Sharpe ratio the best of ``n_trials`` zero-edge strategies is expected to show, when
    the trials' Sharpe ratios have variance ``sharpe_variance``."""
    if n_trials < 1 or sharpe_variance < 0:
        raise ValueError("n_trials must be >= 1 and sharpe_variance >= 0")
    if n_trials == 1:
        return 0.0
    first = _NORMAL.inv_cdf(1.0 - 1.0 / n_trials)
    second = _NORMAL.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return math.sqrt(sharpe_variance) * ((1.0 - EULER_GAMMA) * first + EULER_GAMMA * second)


def deflated_sharpe_ratio(returns: Sequence[float], n_trials: int, sharpe_variance: float) -> float:
    """The probabilistic Sharpe ratio against the best Sharpe that ``n_trials`` lucky strategies
    would reach. Below 0.95, the result is not distinguishable from search luck."""
    return probabilistic_sharpe_ratio(returns, expected_max_sharpe(n_trials, sharpe_variance))


@dataclass(frozen=True)
class LuckTestResult:
    observed: float
    null: FloatArray
    p_value: float


def luck_test(
    observed_best: float,
    search_on_noise: Callable[[np.random.Generator], float],
    *,
    trials: int = 200,
    seed: int | None = None,
) -> LuckTestResult:
    """How often does the same search, run on edge-free data, find something as good?

    ``search_on_noise(rng)`` must destroy the edge (for example flip each trade's direction at
    random, or shuffle days), rerun the *entire* search, and return its best score, so the null
    carries the same number of trials as the real search.
    """
    rng = np.random.default_rng(seed)
    null = np.array([search_on_noise(rng) for _ in range(trials)], dtype=float)
    p = (1 + int(np.sum(null >= observed_best))) / (trials + 1)
    return LuckTestResult(observed_best, null, p)


def holm_adjust(p_values: Sequence[float]) -> FloatArray:
    """Holm step-down adjusted p-values (reject where adjusted p < alpha)."""
    p = np.asarray(p_values, dtype=float)
    m = p.size
    order = np.argsort(p)
    stepped = np.maximum.accumulate((m - np.arange(m)) * p[order])
    adjusted = np.empty(m)
    adjusted[order] = np.minimum(stepped, 1.0)
    return adjusted
