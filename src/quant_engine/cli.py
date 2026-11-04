"""Command-line entry points."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from quant_engine.backtest.config import RunConfig
from quant_engine.strategy.loader import StrategyLoadError


def backtest_main(argv: Sequence[str] | None = None) -> int:
    """``qe-backtest CONFIG.toml``: run the backtest a config file describes and print a report."""
    parser = argparse.ArgumentParser(prog="qe-backtest", description=backtest_main.__doc__)
    parser.add_argument("config", type=Path, help="run configuration (TOML)")
    parser.add_argument("--trades", type=Path, help="write the trade list to this CSV")
    parser.add_argument("--equity", type=Path, help="write the equity curve to this CSV")
    args = parser.parse_args(argv)

    try:
        result = RunConfig.from_toml(args.config).run()
    except (OSError, StrategyLoadError, ValueError) as exc:
        print(f"qe-backtest: {exc}", file=sys.stderr)
        return 2

    print(result.report())
    if args.trades:
        result.trades.to_csv(args.trades, index=False)
    if args.equity:
        result.equity.to_csv(args.equity)
    return 0


if __name__ == "__main__":
    sys.exit(backtest_main())
