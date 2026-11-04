"""quant_engine - research and execution engine for intraday Indian index and option strategies.

The package is split into layers that depend only downwards:

    ops        -> notifications, kill switch, scheduling guards
    execution  -> brokers, order handling, persisted state
    validation -> walk-forward splits, sealed hold-outs, Monte Carlo, significance
    backtest   -> event loop, fills, costs, results
    strategy   -> the Strategy interface (concrete strategies are plug-ins)
    data       -> calendars, validation, cleaning, resampling, synthetic markets
    core       -> clocks and shared types

See docs/ARCHITECTURE.md.
"""

__version__ = "0.1.0"
