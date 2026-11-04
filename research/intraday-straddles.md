# Intraday straddles, sold and bought

**Source:** my own · **Instrument:** NIFTY nearest-weekly options · **Tested:** September 2026 ·
**Verdict:** shelved, both directions

## Idea

Sell (and, as a follow-up, buy) the at-the-money straddle after the first five minutes, with VIX as
a regime filter, and find which stops, exits and days, if any, carry an edge.

## Data

Both legs, minute by minute, for every session from August 2020 to September 2026 (1,510 days),
downloaded strike by strike. Folk VIX bands and published practice were collected first (the
common template is a 09:20 straddle with 25% leg stops and a late-afternoon exit). Bhat, Pandey
and Rao (Journal of Futures Markets, 2024) find that short NIFTY options earn overnight and lose
intraday on average.

## Results

- **Selling every day:** naked and held, -Rs 40 a trade; a 35% leg stop, +Rs 130 at 0.5 points of
  slippage but -Rs 34 at 1 point; hedged, -Rs 497. Sellers do better at VIX 14-20.
- **Buying every day:** every one of ten exits loses, -Rs 508 to -Rs 681 a trade, 0 of 7 years
  positive. At VIX below 15 the straddle costs 0.84% of the index and the day moves 0.32%; the move
  beats the premium on 13% of days.
- A 6 x 5 grid of stops and targets on selling: negative in every cell. A long iron fly instead of
  the long straddle: worse at every wing width (more orders, and the wings cap exactly the rare big
  days that option buying lives on).
- **One frozen rule:** expiry days only, sell naked at 09:20, 35% leg stop. Found on 904 seen days
  (+7.4 points a trade, t 2.8). On the 121 unseen expiry days: **+2.4 points, t 0.78**, below the
  pre-registered t >= 2. Weak, not passed.

## What I learned

- A pricing trap: hedge legs that drifted outside the downloaded +/-500-point window lost their
  prices, and those were the losing legs. Filling them from Black-76 at each leg's own implied
  volatility corrected a result that had been inflated by about Rs 390 a trade.
- Put-call parity cannot rebuild a missing leg from this data: the implied forward minus spot moves
  a median 11 points intraday, against a typical straddle day of about 25 points.
- When target and stop are balanced, a straddle is a coin flip before costs, and costs are 3-4% of
  the premium. Costs alone decide it.
