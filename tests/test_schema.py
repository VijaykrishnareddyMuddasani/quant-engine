import numpy as np
import pandas as pd
import pytest

from quant_engine.data import (
    DataValidationError,
    ExchangeCalendar,
    ValidationReport,
    normalize_columns,
    validate_ohlcv,
)
from support import BarFactory


def checks(report: ValidationReport) -> list[str]:
    return [issue.check for issue in report.issues]


def test_clean_bars_pass(make_bars: BarFactory, calendar: ExchangeCalendar) -> None:
    report = validate_ohlcv(make_bars(), calendar, require_volume=True)
    assert report.ok, str(report)


def test_structural_problems_are_reported_alone(make_bars: BarFactory) -> None:
    bars = make_bars()
    assert checks(validate_ohlcv(bars.drop(columns="high"))) == ["missing_columns"]
    assert checks(validate_ohlcv(bars.reset_index(drop=True))) == ["index_not_datetime"]
    assert checks(validate_ohlcv(bars.tz_localize(None))) == ["index_not_timezone_aware"]


def test_volume_is_only_required_on_request(make_bars: BarFactory) -> None:
    no_volume = make_bars().drop(columns="volume")
    assert validate_ohlcv(no_volume).ok
    assert checks(validate_ohlcv(no_volume, require_volume=True)) == ["missing_columns"]


def test_inconsistent_prices_are_counted_with_examples(make_bars: BarFactory) -> None:
    bars = make_bars()
    bars.iloc[3, bars.columns.get_loc("high")] = bars["close"].iloc[3] - 1
    bars.iloc[5, bars.columns.get_loc("low")] = bars["open"].iloc[5] + 1
    bars.iloc[6, bars.columns.get_loc("volume")] = -1
    report = validate_ohlcv(bars)
    assert checks(report) == [
        "high_below_open_or_close",
        "low_above_open_or_close",
        "negative_volume",
    ]
    assert report.issues[0].count == 1
    assert report.issues[0].examples == (bars.index[3],)


def test_order_and_duplicates(make_bars: BarFactory) -> None:
    bars = make_bars(n=5)
    shuffled = bars.iloc[[0, 2, 1, 3, 3]]
    assert checks(validate_ohlcv(shuffled)) == ["not_sorted", "duplicate_timestamp"]


def test_blank_bars_are_allowed_but_partial_ones_are_not(make_bars: BarFactory) -> None:
    bars = make_bars()
    bars.iloc[2, :4] = np.nan  # blanked on purpose by a repair
    assert validate_ohlcv(bars).ok
    assert checks(validate_ohlcv(bars, allow_blank=False)) == ["blank_bar"]
    bars.iloc[4, bars.columns.get_loc("close")] = np.nan
    assert checks(validate_ohlcv(bars)) == ["partial_nan_prices"]


def test_bars_outside_the_session_need_a_calendar_to_be_seen(
    make_bars: BarFactory, calendar: ExchangeCalendar
) -> None:
    late = make_bars(start="15:28", n=4)  # the last two minutes are after the close
    assert validate_ohlcv(late).ok
    report = validate_ohlcv(late, calendar)
    assert checks(report) == ["outside_session"]
    assert report.issues[0].count == 2


def test_raise_if_failed_names_the_check(make_bars: BarFactory) -> None:
    bars = make_bars()
    bars.iloc[0, 0] = -5.0
    with pytest.raises(DataValidationError, match="non_positive_price"):
        validate_ohlcv(bars).raise_if_failed()


def test_normalize_columns_maps_aliases() -> None:
    raw = pd.DataFrame(columns=["Open", " HIGH ", "l", "Close", "Vol", "OI"])
    assert list(normalize_columns(raw).columns) == ["open", "high", "low", "close", "volume", "oi"]
