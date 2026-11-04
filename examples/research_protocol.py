"""The research protocol end to end, on a synthetic market that has no edge by construction.

1. Cut a year into five chronological segments. Tune on P1 and P2 only; P3 to P5 stay sealed.
2. Walk forward inside the tuning segments: does re-fitting pick parameters that keep working?
3. Luck test: is the best variant better than the best variant on sign-flipped trades?
4. Pre-register the chosen variant with a pass bar, open P3 once, and judge it.
5. Monte Carlo the sealed trades for the spread of drawdowns and losing streaks.

On a random walk the expected outcome is a rejection at step 3 or 4, which is the point: the
protocol has to be able to say no.

    python examples/research_protocol.py
"""

from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from quant_engine.backtest import BacktestConfig, Backtester, BpsCost, FillModel
from quant_engine.backtest.metrics import t_statistic
from quant_engine.data import ExchangeCalendar, SyntheticMarket, resample_session
from quant_engine.strategy.examples import MovingAverageCrossover
from quant_engine.validation import (
    GridSearch,
    HoldoutRegistry,
    PassBar,
    chronological_segments,
    deflated_sharpe_ratio,
    luck_test,
    resample_trades,
    run_walk_forward,
    trading_days_of,
    walk_forward_folds,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = BacktestConfig(fill_model=FillModel(slippage_bps=1.0), costs=BpsCost(2.0))
GRID = [(fast, slow) for fast in (4, 8, 12) for slow in (24, 36, 48)]


def run(bars: pd.DataFrame, params: tuple[int, int]) -> pd.DataFrame:
    fast, slow = params
    return Backtester(MovingAverageCrossover(fast, slow, quantity=50), CONFIG).run(bars).trades


def score(bars: pd.DataFrame, params: tuple[int, int]) -> float:
    return t_statistic(run(bars, params)["net_return_pct"])


def main() -> None:
    calendar = ExchangeCalendar.nse()
    minutes = SyntheticMarket(calendar, seed=21).minute_bars(
        dt.date(2026, 1, 1), dt.date(2026, 12, 31)
    )
    bars = resample_session(minutes, 15, calendar)
    segments = chronological_segments(trading_days_of(bars), 5)
    print("segments:", ", ".join(str(s) for s in segments))
    tuning = pd.concat([segments[0].select(bars), segments[1].select(bars)])

    # 2. walk-forward inside the tuning data only
    folds = walk_forward_folds(trading_days_of(tuning), train_days=40, test_days=20)
    report = run_walk_forward(
        tuning,
        folds,
        GridSearch(GRID, score),
        lambda b, p: Backtester(MovingAverageCrossover(*p, quantity=50), CONFIG).run(b),
    )
    print("\nwalk-forward on P1+P2:\n", report.summary().to_string(index=False))

    # 3. the full grid on P1+P2, then the same grid on sign-flipped trades
    trades = {p: run(tuning, p) for p in GRID}
    scores = {p: t_statistic(t["net_return_pct"]) for p, t in trades.items()}
    best = max(scores, key=lambda p: scores[p])

    def search_on_noise(rng: np.random.Generator) -> float:
        best_noise = -np.inf
        for t in trades.values():
            cost = (t["gross_return_pct"] - t["net_return_pct"]).to_numpy()
            flipped = rng.choice((-1.0, 1.0), len(t)) * t["gross_return_pct"].to_numpy() - cost
            best_noise = max(best_noise, t_statistic(flipped))
        return best_noise

    luck = luck_test(scores[best], search_on_noise, trials=500, seed=1)
    daily = [
        trades[p].groupby(pd.to_datetime(trades[p]["exit_time"]).dt.date)["net_return_pct"].sum()
        for p in GRID
    ]
    sharpes = [d.mean() / d.std() for d in daily if d.std() > 0]
    dsr = deflated_sharpe_ratio(daily[GRID.index(best)], len(GRID), float(np.var(sharpes)))
    print(
        f"\nbest of {len(GRID)}: {best}, t {scores[best]:.2f}; luck-test p {luck.p_value:.3f}; "
        f"deflated Sharpe {dsr:.3f}"
    )

    # 4. pre-register, then open P3 once
    with tempfile.TemporaryDirectory() as folder:
        registry = HoldoutRegistry(Path(folder) / "registry.json")
        reg_id = registry.register(
            family="ma-crossover",
            hypothesis="the best P1+P2 crossover keeps a positive net edge on P3",
            segments=["P3"],
            files=[
                "src/quant_engine/strategy/examples/ma_crossover.py",
                "examples/research_protocol.py",
            ],
            params={"fast": best[0], "slow": best[1], "quantity": 50},
            pass_bar=PassBar(min_trades=30, min_mean=0.0, min_t=2.0),
            root=ROOT,
        )
        registry.open(reg_id, root=ROOT)
        sealed = run(segments[2].select(bars), best)
        verdict = registry.record_result(reg_id, sealed["net_return_pct"])
        print(
            f"\n{reg_id} on P3: {'PASS' if verdict.passed else 'FAIL'} "
            f"({verdict.trades} trades, mean {verdict.mean:.3f}%, t {verdict.t_stat:.2f}) "
            f"{'; '.join(verdict.reasons)}"
        )
        print("P3 is now spent for the family:", sorted(registry.spent("ma-crossover")))

    # 5. Monte Carlo of the sealed trades, positions worth 3x equity (leveraged index futures)
    mc = resample_trades(sealed["net_return_pct"], n_paths=5_000, capital_fraction=3, seed=3)
    print("\nMonte Carlo (5,000 paths):\n", mc.percentiles().round(2).to_string())


if __name__ == "__main__":
    main()
