"""Reading and writing bar files in the engine's layout (CSV, or Parquet with ``pyarrow``)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from quant_engine.core.clock import IST
from quant_engine.data.schema import normalize_columns

TIMESTAMP_COLUMNS = ("timestamp", "datetime", "date", "time")


def _is_parquet(path: Path) -> bool:
    return path.suffix.lower() in {".parquet", ".pq"}


def read_bars(
    path: str | Path, *, tz: dt.tzinfo = IST, timestamp_column: str | None = None
) -> pd.DataFrame:
    """Read bars, normalise column names and return them on a sorted, timezone-aware index.

    Naive timestamps are taken to be exchange-local time in ``tz``; aware ones are converted to it.
    The timestamp comes from ``timestamp_column``, else the first of ``timestamp``, ``datetime``,
    ``date`` or ``time`` present, else the file's index.
    """
    path = Path(path)
    raw = pd.read_parquet(path) if _is_parquet(path) else pd.read_csv(path)
    df = normalize_columns(raw)

    column = (
        timestamp_column.lower()
        if timestamp_column
        else next((c for c in TIMESTAMP_COLUMNS if c in df.columns), None)
    )
    if column is not None:
        stamps = pd.DatetimeIndex(pd.to_datetime(df.pop(column)))
    elif isinstance(df.index, pd.DatetimeIndex):
        stamps = df.index
    else:
        raise ValueError(f"{path}: no timestamp column (looked for {', '.join(TIMESTAMP_COLUMNS)})")

    stamps = stamps.tz_localize(tz) if stamps.tz is None else stamps.tz_convert(tz)
    return df.set_axis(stamps.rename("timestamp")).sort_index()


def write_bars(df: pd.DataFrame, path: str | Path) -> None:
    """Write bars with their timestamps (ISO 8601, with offset) as a ``timestamp`` column."""
    path = Path(path)
    out = df.rename_axis("timestamp")
    if _is_parquet(path):
        out.to_parquet(path)
    else:
        out.to_csv(path, date_format="%Y-%m-%dT%H:%M:%S%z")
