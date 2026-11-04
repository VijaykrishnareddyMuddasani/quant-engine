"""The engine's bar layout, and a validator that reports every way a bar file breaks it.

Layout: a DataFrame with lowercase ``open, high, low, close`` (and usually ``volume``) columns and
a sorted, unique, timezone-aware DatetimeIndex labelling each bar by the start of its interval.

A row whose four prices are all NaN is a *blank*: a bar that a repair removed on purpose (see
``quality.blank``). Blanks are allowed by default; a row with only some prices missing is not.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_engine.data.calendar import ExchangeCalendar

OHLC: tuple[str, ...] = ("open", "high", "low", "close")
OHLCV: tuple[str, ...] = (*OHLC, "volume")

_ALIASES = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "vol": "volume"}


class DataValidationError(ValueError):
    """Raised by ``ValidationReport.raise_if_failed``."""


def datetime_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    """``df``'s index, checked to be a timezone-aware DatetimeIndex."""
    index = df.index
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError("bars need a timezone-aware DatetimeIndex (see validate_ohlcv)")
    return index


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """A copy with column names stripped, lowercased and common aliases (``O``, ``Vol``) mapped."""
    names = {c: _ALIASES.get(str(c).strip().lower(), str(c).strip().lower()) for c in df.columns}
    return df.rename(columns=names)


@dataclass(frozen=True)
class Issue:
    check: str
    count: int
    examples: tuple[pd.Timestamp, ...] = ()
    detail: str = ""

    def __str__(self) -> str:
        text = f"{self.check}: {self.count} row(s)"
        if self.detail:
            text += f" - {self.detail}"
        if self.examples:
            text += " e.g. " + ", ".join(str(t) for t in self.examples)
        return text


@dataclass(frozen=True)
class ValidationReport:
    rows: int
    issues: tuple[Issue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues

    def __str__(self) -> str:
        if self.ok:
            return f"{self.rows} rows, no issues"
        return f"{self.rows} rows, {len(self.issues)} issue(s):\n" + "\n".join(
            f"  {issue}" for issue in self.issues
        )

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise DataValidationError(str(self))


RowCheck = Callable[[pd.DataFrame], "pd.Series[bool]"]


def _row_checks(has_volume: bool, allow_blank: bool) -> dict[str, RowCheck]:
    prices = list(OHLC)
    checks: dict[str, RowCheck] = {
        "duplicate_timestamp": lambda d: pd.Series(d.index.duplicated(), index=d.index),
        "partial_nan_prices": lambda d: (
            d[prices].isna().any(axis=1) & d[prices].notna().any(axis=1)
        ),
        "non_positive_price": lambda d: (d[prices] <= 0).any(axis=1),
        "high_below_open_or_close": lambda d: d["high"] < d[["open", "close"]].max(axis=1),
        "low_above_open_or_close": lambda d: d["low"] > d[["open", "close"]].min(axis=1),
    }
    if not allow_blank:
        checks["blank_bar"] = lambda d: d[prices].isna().all(axis=1)
    if has_volume:
        checks["negative_volume"] = lambda d: d["volume"] < 0
    return checks


def validate_ohlcv(
    df: pd.DataFrame,
    calendar: ExchangeCalendar | None = None,
    *,
    require_volume: bool = False,
    allow_blank: bool = True,
    max_examples: int = 5,
) -> ValidationReport:
    """Check ``df`` against the bar layout. With a ``calendar``, also flag bars outside the session.

    Structural problems (missing columns, a non-datetime or naive index) are reported alone,
    because the row checks cannot run without the structure.
    """
    required = OHLCV if require_volume else OHLC
    missing = [c for c in required if c not in df.columns]
    if missing:
        return ValidationReport(len(df), (Issue("missing_columns", 0, detail=", ".join(missing)),))
    if not isinstance(df.index, pd.DatetimeIndex):
        detail = f"index is {type(df.index).__name__}, not DatetimeIndex"
        return ValidationReport(len(df), (Issue("index_not_datetime", 0, detail=detail),))
    if df.index.tz is None:
        detail = "localize the index to the exchange timezone"
        return ValidationReport(len(df), (Issue("index_not_timezone_aware", 0, detail=detail),))

    issues = []

    def add(check: str, mask: np.ndarray | pd.Series, detail: str = "") -> None:
        flags = np.asarray(mask, dtype=bool)
        if flags.any():
            examples = tuple(df.index[flags][:max_examples])
            issues.append(Issue(check, int(flags.sum()), examples, detail))

    order = np.zeros(len(df), dtype=bool)
    order[1:] = np.asarray(df.index[1:] < df.index[:-1])
    add("not_sorted", order, "timestamp earlier than the row before it")

    for name, check in _row_checks("volume" in df.columns, allow_blank).items():
        add(name, check(df))

    if calendar is not None:
        add(
            "outside_session",
            ~calendar.is_open_mask(df.index),
            "on a non-trading day or outside session hours",
        )

    return ValidationReport(len(df), tuple(issues))
