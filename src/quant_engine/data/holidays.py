"""Exchange trading holidays.

NSE and BSE share one list of trading holidays (equity and derivatives alike), published each
December for the following year. Only weekdays are listed; weekends are closed anyway.

A year missing from a list is not an error. Every weekday of it counts as a trading day, and
``ExchangeCalendar.covers`` lets a caller find out that it is guessing. The list goes stale every
year, so ``quality.find_unlisted_closures`` cross-checks it against the data itself.
"""

from __future__ import annotations

import datetime as dt

# Source: the exchanges' 2026 circular as republished by Zerodha's holiday calendar, cross-checked
# against daily index candles (every weekday with no candle up to September 2026 is listed here).
NSE_HOLIDAYS: dict[dt.date, str] = {
    dt.date(2026, 1, 15): "Municipal Corporation Elections in Maharashtra",
    dt.date(2026, 1, 26): "Republic Day",
    dt.date(2026, 3, 3): "Holi",
    dt.date(2026, 3, 26): "Shri Ram Navami",
    dt.date(2026, 3, 31): "Shri Mahavir Jayanti",
    dt.date(2026, 4, 3): "Good Friday",
    dt.date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    dt.date(2026, 5, 1): "Maharashtra Day",
    dt.date(2026, 5, 28): "Bakri Id",
    dt.date(2026, 6, 26): "Muharram",
    dt.date(2026, 9, 14): "Ganesh Chaturthi",
    dt.date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    dt.date(2026, 10, 20): "Dussehra",
    dt.date(2026, 11, 10): "Diwali-Balipratipada",
    dt.date(2026, 11, 24): "Guru Nanak Jayanti",
    dt.date(2026, 12, 25): "Christmas",
}
