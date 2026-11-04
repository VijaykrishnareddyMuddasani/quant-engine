import datetime as dt

import numpy as np
import pandas as pd
import pytest

from quant_engine.core import IST
from quant_engine.data import ExchangeCalendar, Session

REPUBLIC_DAY = dt.date(2026, 1, 26)  # a Monday


def at(day: dt.date, hhmm: str) -> dt.datetime:
    return dt.datetime.combine(day, dt.time.fromisoformat(hhmm), tzinfo=IST)


def test_weekends_and_listed_holidays_do_not_trade(calendar: ExchangeCalendar) -> None:
    assert calendar.is_trading_day(dt.date(2026, 1, 23))  # Friday
    assert not calendar.is_trading_day(dt.date(2026, 1, 24))  # Saturday
    assert not calendar.is_trading_day(REPUBLIC_DAY)
    assert calendar.holiday_name(REPUBLIC_DAY) == "Republic Day"
    assert calendar.holiday_name(dt.date(2026, 1, 23)) is None


def test_next_and_previous_trading_day_skip_weekend_and_holiday(
    calendar: ExchangeCalendar,
) -> None:
    friday, tuesday = dt.date(2026, 1, 23), dt.date(2026, 1, 27)
    assert calendar.next_trading_day(friday) == tuesday
    assert calendar.previous_trading_day(tuesday) == friday


def test_datetimes_are_read_as_their_date(calendar: ExchangeCalendar) -> None:
    assert not calendar.is_trading_day(pd.Timestamp("2026-01-26 10:00", tz=IST))
    assert calendar.holiday_name(dt.datetime(2026, 1, 26, 12, 0)) == "Republic Day"


def test_trading_days_in_january_2026(calendar: ExchangeCalendar) -> None:
    days = calendar.trading_days(dt.date(2026, 1, 1), dt.date(2026, 1, 31))
    # 22 weekdays, less two holidays (15th and 26th)
    assert len(days) == 20
    assert days[0] == dt.date(2026, 1, 1)
    assert days[-1] == dt.date(2026, 1, 30)


def test_minute_index_covers_the_session(calendar: ExchangeCalendar) -> None:
    day = dt.date(2026, 1, 5)
    minutes = calendar.minute_index(day, day)
    assert len(minutes) == calendar.session.minutes == 375
    assert minutes[0] == pd.Timestamp(at(day, "09:15"))
    assert minutes[-1] == calendar.session_close(day) - pd.Timedelta(minutes=1)
    assert str(minutes.tz) == str(IST)


def test_minute_index_of_a_closed_stretch_is_empty(calendar: ExchangeCalendar) -> None:
    weekend = calendar.minute_index(dt.date(2026, 1, 24), dt.date(2026, 1, 25))
    assert weekend.empty
    assert weekend.tz is not None


@pytest.mark.parametrize(
    ("when", "is_open"),
    [
        (at(dt.date(2026, 1, 5), "09:14"), False),
        (at(dt.date(2026, 1, 5), "09:15"), True),
        (at(dt.date(2026, 1, 5), "15:29"), True),
        (at(dt.date(2026, 1, 5), "15:30"), False),
        (at(REPUBLIC_DAY, "10:00"), False),
        (dt.datetime(2026, 1, 5, 4, 0, tzinfo=dt.UTC), True),  # 09:30 IST
    ],
)
def test_is_open(calendar: ExchangeCalendar, when: dt.datetime, is_open: bool) -> None:
    assert calendar.is_open(when) is is_open


def test_is_open_mask_agrees_with_is_open(calendar: ExchangeCalendar) -> None:
    stamps = pd.date_range("2026-01-23 09:00", "2026-01-27 16:00", freq="37min", tz=IST)
    expected = np.array([calendar.is_open(t) for t in stamps])
    assert (calendar.is_open_mask(stamps) == expected).all()


def test_naive_times_are_refused(calendar: ExchangeCalendar) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        calendar.is_open(dt.datetime(2026, 1, 5, 10, 0))
    with pytest.raises(ValueError, match="timezone-aware"):
        calendar.is_open_mask(pd.date_range("2026-01-05 10:00", periods=3, freq="min"))


def test_covers_only_years_with_a_holiday_list(calendar: ExchangeCalendar) -> None:
    assert calendar.covers(dt.date(2026, 6, 1))
    assert not calendar.covers(dt.date(2031, 6, 1))


def test_invalid_sessions_and_weekends_are_rejected() -> None:
    with pytest.raises(ValueError, match="not after open"):
        Session(open=dt.time(10, 0), close=dt.time(9, 0))
    with pytest.raises(ValueError, match="whole minutes"):
        Session(open=dt.time(9, 15, 30))
    with pytest.raises(ValueError, match="weekend"):
        ExchangeCalendar(weekend=range(7))
