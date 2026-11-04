# 5-EMA reversal

**Source:** my own rules · **Instrument:** NIFTY index · **Tested:** October 2026 ·
**Verdict:** no edge, closed

## Idea

A candle that is stretched entirely away from a fast EMA, followed by a candle that breaks it in
the other direction, marks a reversal.

## Rules

5-period EMA on 15-minute closes. Alert: a red candle whose low is above its EMA (mirror: a green
candle whose high is below it). Trigger: the very next candle breaks the alert candle's low and
closes below it; enter at that close. Stop at the trigger candle's far end; no trade if that stop
is more than 0.30% away, or if the break is under 0.05% of price. One trade a day, before a
late-morning cut-off. Targets 1R to 3R, or hold to the close.

## Protocol

Checked day by day on recent sessions, then tuned on 2026 over a grid of 6,144 settings (timeframes
5-30 minutes, EMA 3-20, cut-off, minimum break, stop cap, stretch filter, four exits; 0.03% cost).
Luck benchmark: the same grid on five 200-session windows of 2015-2019.

## Result

- Whole grid: mean net -0.018% a trade (gross +0.012%); 22% of settings positive; none with t >= 2.
- The best setting (t 1.86) sits inside the luck benchmark, whose best-of-grid t ranged 1.37-2.92.
- My rule on 15-minute EMA 5: 2026 (38 trades) between -0.04% and +0.04% depending on the target;
  2015-2019 (219 trades) at 1R, t -2.66.

## What I learned

A grid's best row has to beat the best row of the same grid on other data, not zero. Only a
hold-to-close variant with a stretch filter hinted at anything, and it was too thin to be worth a
sealed segment.
