"""Session-anchored resampling.

``DataFrame.resample("15min")`` anchors bins to the clock: 09:00, 09:15, 09:30 ... With a session
that opens at 09:15 that happens to line up for 15 minutes but not for 10, 20 or 30, where it
produces a first bar that starts before the open and bars no exchange-aware trader would recognise.
Here bins are counted from the session open of each day, and every output bar carries the moment it
became knowable, so look-ahead has to be written on purpose rather than slipping in.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_engine.data.calendar import ExchangeCalendar
from quant_engine.data.schema import OHLC, datetime_index


def resample_session(
    df: pd.DataFrame,
    minutes: int,
    calendar: ExchangeCalendar,
    *,
    drop_incomplete: bool = False,
) -> pd.DataFrame:
    """Aggregate one-minute bars into bins of ``minutes`` counted from each day's session open.

    Output rows are labelled by bin start and carry three extra columns:

    ``available_at``
        The end of the bin (or the session close, for a short last bin): the earliest moment a
        decision may use the bar.
    ``bars``
        How many priced source bars went into it. Blank (NaN) source bars do not count.
    ``complete``
        Whether every minute the bin should contain was present and priced.

    A bin whose source bars are all blank still appears, with NaN prices and ``bars == 0``.
    """
    if minutes <= 0:
        raise ValueError(f"minutes must be positive, got {minutes}")
    if df.empty:
        return df.iloc[0:0]

    local_index = datetime_index(df).tz_convert(calendar.tz)
    outside = ~calendar.is_open_mask(local_index)
    if outside.any():
        raise ValueError(
            f"{int(outside.sum())} bar(s) fall outside the session (first: "
            f"{local_index[outside][0]}); filter or fix them before resampling"
        )

    width = pd.Timedelta(minutes=minutes)
    open_offset = pd.Timedelta(
        hours=calendar.session.open.hour, minutes=calendar.session.open.minute
    )
    day = local_index.normalize()
    bin_start = day + open_offset + ((local_index - day - open_offset) // width) * width

    data = df.set_axis(local_index)
    priced = data[list(OHLC)].notna().all(axis=1).to_numpy()
    grouped = data[priced].groupby(bin_start[priced])
    aggregations = {
        "open": ("open", "first"),
        "high": ("high", "max"),
        "low": ("low", "min"),
        "close": ("close", "last"),
    }
    if "volume" in data.columns:
        aggregations["volume"] = ("volume", "sum")
    out = grouped.agg(**aggregations)
    out["bars"] = grouped.size()

    all_bins = pd.DatetimeIndex(bin_start.unique()).sort_values()
    out = out.reindex(all_bins)
    out["bars"] = out["bars"].fillna(0).astype(int)

    session_close = all_bins.normalize() + pd.Timedelta(
        hours=calendar.session.close.hour, minutes=calendar.session.close.minute
    )
    bin_end = all_bins + width
    out["available_at"] = bin_end.where(bin_end <= session_close, session_close)
    expected = np.asarray((out["available_at"] - all_bins) / pd.Timedelta(minutes=1)).astype(int)
    out["complete"] = out["bars"].to_numpy() == expected
    out.index.name = df.index.name

    if drop_incomplete:
        out = out[out["complete"]]
    return out
