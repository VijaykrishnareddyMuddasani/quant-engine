"""Chronological segments: the unit of the research protocol.

History is cut into equal, back-to-back segments of *trading days*. An idea is tuned on some of
them and tested once on the others. Counting trading days, rather than calendar time or bars,
gives every segment the same number of sessions whatever the holidays.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_engine.data.calendar import as_date
from quant_engine.data.schema import datetime_index


@dataclass(frozen=True)
class Segment:
    name: str
    start: dt.date
    end: dt.date  # inclusive

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"segment {self.name} ends before it starts")

    def contains(self, day: dt.date) -> bool:
        return self.start <= as_date(day) <= self.end

    def select(self, bars: pd.DataFrame) -> pd.DataFrame:
        """The rows of ``bars`` whose exchange-local date falls in the segment."""
        days = datetime_index(bars).normalize().date
        mask = (days >= self.start) & (days <= self.end)
        return bars[mask]

    def __str__(self) -> str:
        return f"{self.name} {self.start} to {self.end}"


def trading_days_of(bars: pd.DataFrame) -> list[dt.date]:
    """The distinct exchange-local dates present in ``bars``, in order."""
    return sorted(set(datetime_index(bars).normalize().date))


def chronological_segments(days: Sequence[dt.date], n: int, prefix: str = "P") -> list[Segment]:
    """Cut ``days`` into ``n`` back-to-back segments whose sizes differ by at most one day."""
    if n < 1:
        raise ValueError("need at least one segment")
    if len(days) < n:
        raise ValueError(f"cannot cut {len(days)} days into {n} segments")
    ordered = sorted(as_date(d) for d in days)
    chunks = np.array_split(np.arange(len(ordered)), n)
    return [
        Segment(f"{prefix}{k + 1}", ordered[int(chunk[0])], ordered[int(chunk[-1])])
        for k, chunk in enumerate(chunks)
    ]


def draw_segments(segments: Sequence[Segment], k: int, seed: int) -> list[Segment]:
    """Pick ``k`` segments at random, without replacement, returned in time order.

    The seed belongs in the pre-registration, so anyone can check the draw was not chosen after the
    fact.
    """
    if not 0 < k <= len(segments):
        raise ValueError(f"cannot draw {k} of {len(segments)} segments")
    rng = np.random.default_rng(seed)
    picked = rng.choice(len(segments), size=k, replace=False)
    return sorted((segments[int(i)] for i in picked), key=lambda s: s.start)
