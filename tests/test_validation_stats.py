import numpy as np
import pytest

from quant_engine.validation import (
    bootstrap_ci,
    bootstrap_indices,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    holm_adjust,
    luck_test,
    probabilistic_sharpe_ratio,
    resample_trades,
    sign_flip_p_value,
)
from quant_engine.validation.montecarlo import longest_run

RNG = np.random.default_rng(0)
EDGE = RNG.normal(0.2, 1.0, 400)
NOISE = RNG.normal(0.0, 1.0, 400)


def test_block_bootstrap_keeps_neighbours_together() -> None:
    idx = bootstrap_indices(10, 12, 50, np.random.default_rng(1), block=4)
    assert idx.shape == (50, 12)
    assert idx.min() >= 0
    assert idx.max() <= 9
    assert ((idx[:, 1] - idx[:, 0]) % 10 == 1).all()  # inside a block, consecutive (circular)


def test_longest_run() -> None:
    mask = np.array([[True, True, False, True], [False, False, False, False], [True] * 4])
    assert longest_run(mask).tolist() == [2, 0, 4]


def test_monte_carlo_of_winners_only_has_no_drawdown() -> None:
    report = resample_trades([1.0, 2.0, 0.5], n_paths=200, seed=1)
    assert (report.max_drawdown_pct == 0).all()
    assert (report.longest_losing_streak == 0).all()
    assert report.ruin_probability == 0


def test_monte_carlo_measures_ruin_and_is_reproducible() -> None:
    returns = [10.0, -30.0, 5.0, -20.0]
    a = resample_trades(returns, n_paths=2_000, n_trades=20, ruin_drawdown_pct=50, seed=4)
    b = resample_trades(returns, n_paths=2_000, n_trades=20, ruin_drawdown_pct=50, seed=4)
    assert np.array_equal(a.max_drawdown_pct, b.max_drawdown_pct)
    assert 0.5 < a.ruin_probability < 1.0
    assert list(a.percentiles().columns) == ["p5", "p25", "p50", "p75", "p95"]


def test_bootstrap_ci_brackets_the_mean() -> None:
    low, high = bootstrap_ci(EDGE, n_resamples=2_000, seed=1)
    assert low < EDGE.mean() < high
    assert low > 0


def test_sign_flips_separate_an_edge_from_noise() -> None:
    assert sign_flip_p_value(EDGE, n_resamples=2_000, seed=1) < 0.01
    assert sign_flip_p_value(NOISE, n_resamples=2_000, seed=1) > 0.05


def test_probabilistic_and_deflated_sharpe() -> None:
    assert probabilistic_sharpe_ratio(EDGE) > 0.99
    assert expected_max_sharpe(1, 0.01) == 0.0
    assert expected_max_sharpe(1_000, 0.01) > expected_max_sharpe(10, 0.01) > 0
    one_try = deflated_sharpe_ratio(EDGE, n_trials=1, sharpe_variance=0.01)
    many_tries = deflated_sharpe_ratio(EDGE, n_trials=10_000, sharpe_variance=0.01)
    assert many_tries < one_try


def test_luck_test_tells_a_real_best_from_a_lucky_one() -> None:
    def best_of_twenty_noise(rng: np.random.Generator) -> float:
        return float(max(rng.normal(0, 1, 400).mean() for _ in range(20)))

    real = luck_test(EDGE.mean(), best_of_twenty_noise, trials=200, seed=2)
    lucky = luck_test(float(NOISE.mean()), best_of_twenty_noise, trials=200, seed=2)
    # A t of about 3 on one sample is only just clear of the best of twenty coin tosses.
    assert real.p_value < 0.05
    assert lucky.p_value > 0.5


def test_holm_adjustment() -> None:
    adjusted = holm_adjust([0.01, 0.04, 0.03, 0.005])
    assert adjusted.tolist() == pytest.approx([0.03, 0.06, 0.06, 0.02])
