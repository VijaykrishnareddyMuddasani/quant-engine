# Central Pivot Range setups

**Source:** setups taught in a paid Indian trading course, described here in my own words ·
**Instrument:** NIFTY index; 95 stocks · **Tested:** September-October 2026 ·
**Verdict:** every frozen rule failed, closed

## Idea

The Central Pivot Range (CPR) is three levels computed from the previous session's range and close.
The teaching: a narrow CPR, or one inside or entirely above or below the previous day's, comes before
a trending day (trade breakouts); a wide or overlapping CPR means no trade; and some setups (a
"virgin" CPR that price never touched, a failed push at the first resistance or support) call for
mean reversion. The course gives setups, not trade rules, so entries, stops and targets were designed
separately and varied.

## Protocol

NIFTY minute data cut into five segments; tuning on P1+P3, sealed P2, P4 and P5. Each frozen
candidate was pre-registered and run once.

## Result

- **The premise first:** on 1,134 sessions, CPR width does not predict a trending day. Range
  expansion and directional efficiency are flat across every width decile (|Spearman| <= 0.03).
- Inside-CPR days are rare (4% of days) and only slightly more trending (t 1.8).
- **Breakout rules, frozen and run on P5:** all four failed (best -0.023% a trade, t -0.79). All
  breakout rules combined: -0.010% a trade (t -0.26).
- **Mean reversion:** virgin-CPR days gave 12-58 trades and nothing; the "attract" fade passed no
  tuning bar, and a short-side version failed on 95 stocks.

## What I learned

Test the premise before the trade rules. If the claimed cause (narrow CPR leads to a trend day) does
not show up in the data at the level of whole days, no entry rule built on it is likely to survive.
