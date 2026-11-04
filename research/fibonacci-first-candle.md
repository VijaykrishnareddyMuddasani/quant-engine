# Fibonacci levels on the first candle

**Source:** a chart shared with me, and a rule I heard · **Instrument:** NIFTY weekly options ·
**Tested:** October 2026 · **Verdict:** coin toss, closed

## Idea

Draw Fibonacci levels on the first 12-minute candle (low to high for a green candle, high to low for
a red one), then trade the 5-minute chart against them: enter when the 0 level is broken with a
target at -0.55, or wait for a pull-back to 0.55 after the break and target -0.55 from there.

## Protocol

Seven families (A-G) and 46 settings, including retests, fades and "golden zone" entries. Stage 1:
NIFTY moves in basis points against a coin-flip benchmark. Stage 2: the same trades priced on
recorded option premiums. Option segments P2+P3 (601 sessions); P1, P4 and P5 never opened. Two
independent implementations of the main rules matched trade for trade.

## Result

- **Target-hit rates equal what a driftless random walk gives from the same distances**: 62%
  against 63% for the break rule, 23% against 29% for the pull-back rule.
- On option prices, per lot per trade after costs: break rule -Rs 234 (t -2.4, 190 trades a year);
  pull-back rule -Rs 530 (t -3.3); retest -291; fade -286; other end -398; golden zone -478.
- The only positive variants were a no-target hold to the close (one segment only, and decaying) and
  one fade (+Rs 38, t 0.25).

## What I learned

The right benchmark for a target-and-stop rule is the hit rate a random walk gives over the same
distances. If the levels do not change those odds, they are decoration.
