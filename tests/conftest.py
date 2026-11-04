from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from quant_engine.data import ExchangeCalendar
from support import MONDAY, BarFactory


@pytest.fixture
def calendar() -> ExchangeCalendar:
    return ExchangeCalendar.nse()


@pytest.fixture
def make_bars(calendar: ExchangeCalendar) -> BarFactory:
    """Minute bars rising by ``step`` each minute, with a fixed wick either side of the body."""

    def make(
        day: dt.date = MONDAY,
        start: str = "09:15",
        n: int = 10,
        price: float = 100.0,
        step: float = 1.0,
        volume: int = 10,
    ) -> pd.DataFrame:
        first = pd.Timestamp.combine(day, dt.time.fromisoformat(start))
        index = pd.date_range(first, periods=n, freq="min").tz_localize(calendar.tz)
        close = price + step * np.arange(1, n + 1)
        open_ = close - step
        return pd.DataFrame(
            {
                "open": open_,
                "high": np.maximum(open_, close) + 0.5,
                "low": np.minimum(open_, close) - 0.5,
                "close": close,
                "volume": volume,
            },
            index=index,
        )

    return make
