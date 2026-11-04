"""Shared constants and types for the tests (fixtures live in conftest.py)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pandas as pd

MONDAY = dt.date(2026, 1, 5)

BarFactory = Callable[..., pd.DataFrame]
