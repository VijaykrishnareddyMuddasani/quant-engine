# Overnight credit-spread algo

**Source:** a commercial algo sold by a SEBI-registered research analyst on a broker's algo
marketplace · **Instrument:** NIFTY weekly option spreads, held overnight · **Tested:** October 2026 ·
**Verdict:** the rebuilt rule fails, closed

## Idea

The product publishes its full trade list (214 trades, July 2025 to October 2026). Can its rule be
recovered from the list, and does the rule hold on earlier years?

## Method

- The published trades priced with realistic costs: +Rs 879 a trade as published (t 3.29), **+Rs 558
  after costs (t 2.09)**, about 171 trades a year. **All of the profit came from the bearish side,
  while NIFTY fell about 12%**; the worst trade lost Rs 13,100 a lot on a weekend gap.
- The rule was read off the trade list and matched to it entry by entry, never fitted to profit: a
  short-term rank-based momentum signal decides the side; sell a near strike and buy one further out;
  take profit or stop at fixed fractions of the index; exit the next day. Two readings of one
  ambiguous input matched 68% and 75% of the published entries; both were carried forward.

## Result

- The untuned rebuild on option segments P2+P3 (604 sessions): **-Rs 122 a trade (t -0.64)** and
  -Rs 250 (t -1.34) for the two readings. The direction call is a coin toss.
- About 3,150 tuning outcomes found nothing consistent; the one filter that looked good on P2+P3 was
  about zero on recent data and was not adopted.
- A frozen run on P1+P4, with the bar written first (positive in each segment, t >= 2 combined):
  failed.

## What I learned

A short live record in a one-directional market measures the market's direction, not the method.
Rebuilding from the trade list was cheaper than buying the product and gave a clear answer.
