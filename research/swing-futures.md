# Swing rules on NIFTY futures

**Source:** 16 textbook trend and swing rules · **Instrument:** NIFTY futures, holds of 5+ days ·
**Tested:** September 2026 · **Verdict:** shelved

## Protocol

Daily data 1995-2026, fills at the next open, costs, monthly rolls, and futures carry (longs pay it,
shorts receive it). The carry was calibrated on 785 days of exchange bhavcopy data: a median 4.6% a
year (2-7% by year). Split fixed before the run: design 1996-2015, hold-out 2016-2026. The target was
a rule I could hold through a drawdown of Rs 1 lakh.

## Result

- Best on design (by Sharpe): Supertrend (10, 3), long only. Hold-out: **3.3% a year against 3.8%
  for buy-and-hold**, worst drawdown -28% against -40%, in the market 60% of the time. t about 1.2:
  a smaller drawdown, not an edge.
- Shorting NIFTY lost under almost every rule, in both periods.
- Carry is large: it takes buy-and-hold from about 10% to about 4% a year of notional.
- Follow-ups (buying after VIX spikes; a protective put; option versions): every futures version
  broke the Rs 1 lakh drawdown limit (one lot is about Rs 15 lakh of notional); the best VIX-spike
  rule made money in both halves but its worst trade was -Rs 4.9 lakh (March 2020).

## What I learned

On an index future, trend rules mostly buy a smaller drawdown with a smaller return. The carry has
to be in the backtest; without it every long rule looks about twice as good.
