# quant-engine

A research and execution engine for intraday strategies on Indian index and index-option markets
(NSE / BSE), written in typed, tested Python.

Work in progress. This first stage holds the data layer (exchange calendar, OHLCV validation,
data-quality checks, session-anchored resampling, a synthetic market) and the repository tooling.

```bash
pip install -e ".[dev]"
pytest
```
