# Volume-profile swing breakouts

**Source:** my own · **Instrument:** ICICI Bank, Reliance, L&T, Infosys, SBI (cash) ·
**Tested:** September 2026 · **Verdict:** no edge over drift, closed

## Idea

Price "moves freely" once it leaves a fixed-range volume-profile zone, so a close above the zone
should start a swing.

## Rules

Zone = value area (50% or 70% of volume) of the previous 10, 20 or 40 sessions, built from real
one-minute volume. Buy at the next open after a close above the zone; exit on a close back below
its middle, below its top, or after 20 days. 0.25% round-trip cost. Benchmark: the stock's own
drift over the same holding days. Control: a plain N-day-high breakout.

## Protocol

Tune on one stock (Reliance, 2015-2021), check on a second (ICICI Bank), then one frozen setting on
all five for 2022-2024. 2025 onwards sealed.

## Result

- Reliance: +2% to +6% a trade, but nearly all of it the stock's drift; best excess t 1.07.
- Only 1 of 18 settings positive on both design stocks (chance alone would give 4-5).
- Frozen setting, 2022-2024, 122 trades: **excess -0.54% a trade (t -1.03)**, 23% winners. The
  plain breakout: -1.06% (t -1.17).
- A follow-up with an anchored swing profile, dip buying and a market-trend filter: excess +0.05%
  (t 0.04) on the check years.

## What I learned

Against a drift benchmark, the box adds nothing to simply being invested. With 25-60 trades per
stock per period the test can rule out a large edge, not a small one; the sealed years were left
unopened for a genuinely new swing idea.
