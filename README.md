# quant-engine

[![ci](https://github.com/VijaykrishnareddyMuddasani/quant-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/VijaykrishnareddyMuddasani/quant-engine/actions/workflows/ci.yml)

A research and execution engine for intraday strategies on Indian index and index-option markets
(NSE / BSE), written in typed, tested Python.

The infrastructure here is rebuilt from a live intraday index-options trading system I run on
Zerodha. The strategies that system trades are private and are not part of this repository.

## What is in it

- **A data layer that does not trust its data.** Exchange calendar, OHLCV validation, detectors for
  hazards found in real vendor data (frozen bars around the closing auction, carried option prices
  on untraded minutes, missing minutes, unlisted holidays), session-anchored resampling with
  explicit `available_at` times so look-ahead cannot creep in, and a synthetic market with
  volatility clustering, fat tails, overnight gaps and a U-shaped intraday volatility profile.
- **An event-driven backtester that refuses to flatter.** Orders fill from the next bar only;
  stops that gap fill at the open, not the trigger; limits must trade through; a stop and a target
  in the same bar resolve to the stop; protective stops placed on entry can be hit in the entry
  bar. Indian statutory charge schedules, round-trip trade accounting, runs described in TOML.
- **Strategies as plug-ins.** A strategy implements one small interface and is loaded by import
  path, so private strategy code lives in its own package and never enters this repository.
- **Research discipline as code.** Chronological segments, a registry of pre-registered sealed
  hold-outs locked by SHA-256 hashes (a segment, once opened, is spent), luck tests that rerun the
  whole search on edge-free data, deflated and probabilistic Sharpe ratios, Holm corrections, block
  bootstrap Monte Carlo of drawdowns, losing streaks and ruin, and walk-forward with trial counting.
- **Execution built for things going wrong.** A broker protocol with Kite and simulated
  implementations; order chasing at the touch; idempotent placement (a timed-out order is looked
  for, never blindly re-sent); multi-leg orders that buy protection first and roll back on failure;
  atomic state that is reconciled with the broker before a restart may trade; broker-side backstops
  behind engine-managed stops; a live runner that drives the same strategy object as the backtest.
- **Operations.** Telegram control (status, stop, skip, takeover with confirmation) that obeys one
  chat and ignores stale commands; a kill switch whose requests expire with the day; a rest-day
  guard that fails toward running; preflight checks; a supervisor that closes a book after repeated
  errors; `qe-live`, paper unless `--live` is typed; systemd and cron deployment.
- **A research log** of [16 ideas I tested and closed](research/README.md), from my own and from
  books, a course, a friend, papers and paid products, with the protocol each went through and what
  each failure taught.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

## Quick start

```bash
pip install -e ".[dev]"
pytest
qe-backtest examples/ma_crossover.toml
python examples/research_protocol.py      # segments, walk-forward, luck test, sealed hold-out, Monte Carlo
qe-guard --date 2026-01-26                # a listed holiday: prints the reason, exits 10
```

The example is a textbook moving-average crossover on a synthetic index. It loses money after
costs, which is the expected result for a crossover on a random walk and a useful check that the
costs are being charged.

Working with bars directly:

```python
import datetime as dt
from quant_engine.backtest import Backtester, BacktestConfig, BpsCost, FillModel
from quant_engine.data import ExchangeCalendar, SyntheticMarket, resample_session, validate_ohlcv
from quant_engine.strategy.examples import MovingAverageCrossover

cal = ExchangeCalendar.nse()
minutes = SyntheticMarket(cal, seed=7).minute_bars(dt.date(2026, 1, 1), dt.date(2026, 3, 31))
validate_ohlcv(minutes, cal).raise_if_failed()
bars = resample_session(minutes, minutes=15, calendar=cal)

config = BacktestConfig(fill_model=FillModel(slippage_bps=1.0), costs=BpsCost(2.0))
result = Backtester(MovingAverageCrossover(fast=8, slow=21, quantity=50), config).run(bars)
print(result.report())
```

## Plugging in a strategy

```python
# my_strategies/books.py - in its own (private) package
from quant_engine.strategy import Strategy, StrategyContext, trade_to


class MyBook(Strategy):
    def on_bar(self, bar, ctx: StrategyContext) -> None:
        history = ctx.history(50)  # completed bars only, the current one last
        ...
        trade_to(ctx, target=50, tag="why this trade")
```

```toml
# my_strategies/run.toml
[strategy]
spec = "my_strategies.books:MyBook"
```

Install the package with `pip install -e path/to/my_strategies`, then run
`qe-backtest path/to/my_strategies/run.toml`. The engine never imports it by name.

## Layout

```
src/quant_engine/
  core/        clocks, value types (bars, orders, fills, trades), crash-safe JSON files
  data/        calendar, schema validation, quality checks, resampling, synthetic market, file IO
  strategy/    the Strategy interface, the import-path loader, textbook examples
  backtest/    engine, fill model, charge schedules, ledger, metrics, results, TOML run config
  validation/  segments, hold-out registry, walk-forward, Monte Carlo, significance tests
  execution/   broker protocol, Kite and simulated brokers, order execution, multi-leg orders,
               state and reconciliation, live runner, Kite candle feed
  ops/         notifications, Telegram bot, kill switch, rest-day guard, preflight, supervisor,
               qe-live
  devtools/    leak guard
  cli.py       qe-backtest
examples/      run configurations and the research-protocol walk-through
research/      the research log
deploy/        systemd unit, cron table, start script
tests/         pytest suite: no network, no vendor data
docs/          architecture
```

Commands: `qe-backtest`, `qe-live`, `qe-bot`, `qe-guard`, `qe-leak-guard`.

## How this was built

I designed the research and the system; the code was written with AI assistance (Claude), and
every part of it is tested and explained in this repository.

## What is deliberately not here

- **Strategy code and parameters.** Only textbook examples ship here.
- **Market data.** Vendor data cannot be redistributed. Tests and examples use the synthetic market;
  the loaders read your own files.

## Licence

MIT, see [LICENSE](LICENSE).
