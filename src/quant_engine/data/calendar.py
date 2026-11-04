"""Exchange calendar: which days trade, and when the session runs.

All timestamps the calendar hands out are timezone-aware in the exchange's timezone. Days can be
given as ``date``, ``datetime`` or ``pandas.Timestamp``; only the date part is used.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from quant_engine.core.clock import IST
from quant_engine.data.holidays import NSE_HOLIDAYS

ONE_DAY = dt.timedelta(days=1)


def _minute_of_day(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def as_date(day: dt.date) -> dt.date:
    """The calendar date of a date, datetime or Timestamp (a datetime is never equal to a date)."""
    return day.date() if isinstance(day, dt.datetime) else day


@dataclass(frozen=True)
class Session:
    """Regular trading hours: ``open`` is the first minute, ``close`` the end of the last one."""

    open: dt.time = dt.time(9, 15)
    close: dt.time = dt.time(15, 30)

    def __post_init__(self) -> None:
        for t in (self.open, self.close):
            if t.second or t.microsecond:
                raise ValueError(f"session times must be whole minutes, got {t}")
        if self.close <= self.open:
            raise ValueError(f"session close {self.close} is not after open {self.open}")

    @property
    def minutes(self) -> int:
        return _minute_of_day(self.close) - _minute_of_day(self.open)


class ExchangeCalendar:
    """Trading days and session times for one exchange."""

    def __init__(
        self,
        holidays: Mapping[dt.date, str] | Iterable[dt.date] = (),
        *,
        session: Session | None = None,
        tz: dt.tzinfo = IST,
        listed_years: Iterable[int] | None = None,
        weekend: Iterable[int] = (5, 6),
    ) -> None:
        if isinstance(holidays, Mapping):
            self._holidays = {as_date(d): str(name) for d, name in holidays.items()}
        else:
            self._holidays = {as_date(d): "holiday" for d in holidays}
        self.session = session or Session()
        self.tz = tz
        self.weekend = frozenset(weekend)
        if len(self.weekend) >= 7 or not self.weekend <= set(range(7)):
            raise ValueError(f"weekend must be a proper subset of weekdays 0-6, got {weekend}")
        years = listed_years if listed_years is not None else (d.year for d in self._holidays)
        self.listed_years = frozenset(years)

    @classmethod
    def nse(cls) -> ExchangeCalendar:
        """NSE / BSE: 09:15-15:30 IST, Saturday and Sunday closed, the published holiday list."""
        return cls(NSE_HOLIDAYS)

    # --- days ---------------------------------------------------------------------------------

    def covers(self, day: dt.date) -> bool:
        """Whether this day's year has a holiday list (if not, every weekday is assumed open)."""
        return as_date(day).year in self.listed_years

    def holiday_name(self, day: dt.date) -> str | None:
        return self._holidays.get(as_date(day))

    def is_trading_day(self, day: dt.date) -> bool:
        d = as_date(day)
        return d.weekday() not in self.weekend and d not in self._holidays

    def trading_days(self, start: dt.date, end: dt.date) -> list[dt.date]:
        """Trading days from ``start`` to ``end``, both included."""
        first, last = as_date(start), as_date(end)
        days = []
        day = first
        while day <= last:
            if self.is_trading_day(day):
                days.append(day)
            day += ONE_DAY
        return days

    def next_trading_day(self, day: dt.date) -> dt.date:
        """The first trading day strictly after ``day``."""
        d = as_date(day) + ONE_DAY
        while not self.is_trading_day(d):
            d += ONE_DAY
        return d

    def previous_trading_day(self, day: dt.date) -> dt.date:
        """The last trading day strictly before ``day``."""
        d = as_date(day) - ONE_DAY
        while not self.is_trading_day(d):
            d -= ONE_DAY
        return d

    # --- times --------------------------------------------------------------------------------

    def session_open(self, day: dt.date) -> pd.Timestamp:
        return pd.Timestamp.combine(as_date(day), self.session.open).tz_localize(self.tz)

    def session_close(self, day: dt.date) -> pd.Timestamp:
        return pd.Timestamp.combine(as_date(day), self.session.close).tz_localize(self.tz)

    def is_open(self, when: dt.datetime) -> bool:
        """Whether the market is in session at ``when`` (a timezone-aware time)."""
        if when.tzinfo is None:
            raise ValueError("is_open needs a timezone-aware time")
        local = when.astimezone(self.tz)
        minute = _minute_of_day(local.time())
        in_hours = _minute_of_day(self.session.open) <= minute < _minute_of_day(self.session.close)
        return in_hours and self.is_trading_day(local.date())

    def is_open_mask(self, index: pd.DatetimeIndex) -> npt.NDArray[np.bool_]:
        """Vectorised ``is_open`` for a timezone-aware index: True where the bar is in session."""
        if index.tz is None:
            raise ValueError("index must be timezone-aware")
        local = index.tz_convert(self.tz)
        minute = np.asarray(local.hour * 60 + local.minute)
        in_hours = (minute >= _minute_of_day(self.session.open)) & (
            minute < _minute_of_day(self.session.close)
        )
        codes, days = pd.factorize(local.normalize())
        trading = np.array([self.is_trading_day(d) for d in days], dtype=bool)
        result: npt.NDArray[np.bool_] = in_hours & trading[codes]
        return result

    def empty_index(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex([], dtype="datetime64[ns]").tz_localize(self.tz)

    def minute_index(self, start: dt.date, end: dt.date) -> pd.DatetimeIndex:
        """The start time of every session minute on the trading days from ``start`` to ``end``."""
        days = self.trading_days(start, end)
        if not days:
            return self.empty_index()
        base = np.array([np.datetime64(d, "m") for d in days])
        offsets = (np.arange(self.session.minutes) + _minute_of_day(self.session.open)).astype(
            "timedelta64[m]"
        )
        grid = (base[:, None] + offsets[None, :]).ravel().astype("datetime64[ns]")
        return pd.DatetimeIndex(grid).tz_localize(self.tz)
