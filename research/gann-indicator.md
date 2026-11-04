# Gann square-of-nine indicator

**Source:** a paid, invite-only TradingView indicator · **Instrument:** NIFTY index, 3-minute bars ·
**Tested:** September 2026 · **Verdict:** no edge, closed

## Idea

The indicator draws supply, demand and target zones around the day's open. Its levels were fitted
from readings of the chart and follow the classic square-of-nine construction:
`(sqrt(open) +/- k * 0.125) ** 2` for a few values of `k`.

## Protocol

Two families on September 2024 to September 2026, with 1.5 points of cost: breakouts through a zone
and rejections from it. The control: the same rules on levels shifted by random amounts. A follow-up
idea (a failed break of the indicator's other lines, then a reversal) was tested over 24 combinations
of timeframe, setup and exit.

## Result

- Breakouts: t -0.10. Rejections: t -1.81.
- **The real levels did worse than randomly shifted levels**: they beat only 20% (breakouts) and 30%
  (rejections) of the random controls.
- The failed-break reversal: best t 0.99 of 24 combinations, chance level, and no better than the
  same rule without the indicator's lines.

## What I learned

A level-based method has to beat the same rules at random levels before its levels mean anything.
These did not.
