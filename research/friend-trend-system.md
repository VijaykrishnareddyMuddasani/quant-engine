# Hourly trend system

**Source:** a friend's one-page strategy report · **Instrument:** NIFTY weekly options ·
**Tested:** October 2026 · **Verdict:** no edge, closed

## Idea

Trade 5-minute crosses of a volume-weighted moving average in the direction of the hourly trend,
by buying an option. The report claimed 308 trades in 22 months, 43.5% winners and about Rs 75,000
on one lot (about Rs 243 a trade, unverified).

## Rules as the report states them (long side; short mirrors with puts)

1. Hourly chart: VWMA-20 above the Supertrend (10, 3) line.
2. 5-minute close in the top 30% of the last 20 candles' range.
3. Trigger: a 5-minute close crossing above VWMA-20 with the Supertrend green.

Buy a next-week option slightly in the money; stop 15 premium points; at +15 move the stop to entry
+2; no target; at most three trades a day; all out late in the day. Where the report was silent
(how stops are checked, entry window, re-entry, the volume behind the VWMA) the variants were
written down before running and each was tested.

## Protocol

Option segments P2+P3 (604 sessions, October 2021 to April 2024), recorded premiums, both the
nearest-week and next-week expiry. Minute volume for expired futures is not available from either
data vendor, so the VWMA was run with a stand-in (summed turnover of the index stocks) and with no
volume at all: if the verdict is the same both ways, the gap does not matter.

## Result

- Next-week options: **-Rs 29 a trade, t -0.25**. Nearest week: -Rs 31 (t -0.26) over 321 trades.
- The index's own move after a signal: +0.5 bps after 30 minutes, -3.9 bps by the close. No direction.
- A 10-period VWMA reproduces the report's trade count (841 trades) and loses Rs 179 a trade (t -2.6).
- 23 one-change variants, each with and without volume: nothing.

## What I learned

Matching a report's trade count is not matching its result. When a rule needs data that cannot be
had, test whether the verdict depends on it before buying any.
