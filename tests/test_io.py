from pathlib import Path

import pandas as pd
import pytest

from quant_engine.core import IST
from quant_engine.data import read_bars, write_bars
from support import MONDAY, BarFactory


def test_csv_round_trip(make_bars: BarFactory, tmp_path: Path) -> None:
    bars = make_bars()
    path = tmp_path / "bars.csv"
    write_bars(bars, path)
    back = read_bars(path)
    pd.testing.assert_frame_equal(
        back, bars, check_freq=False, check_names=False, check_index_type=False
    )
    assert str(back.index.tz) == str(IST)


def test_naive_times_are_exchange_time_and_aware_ones_are_converted(tmp_path: Path) -> None:
    naive = tmp_path / "naive.csv"
    naive.write_text("Date,Open,High,Low,Close\n2026-01-05 09:15:00,1,2,0.5,1.5\n")
    assert read_bars(naive).index[0] == pd.Timestamp(f"{MONDAY} 09:15", tz=IST)

    utc = tmp_path / "utc.csv"
    utc.write_text("timestamp,open,high,low,close\n2026-01-05T03:45:00+00:00,1,2,0.5,1.5\n")
    assert read_bars(utc).index[0] == pd.Timestamp(f"{MONDAY} 09:15", tz=IST)


def test_a_file_without_timestamps_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "no_time.csv"
    path.write_text("open,high,low,close\n1,2,0.5,1.5\n")
    with pytest.raises(ValueError, match="no timestamp column"):
        read_bars(path)
