# EMA 9/20 crossover

**Source:** my own (a textbook signal) · **Instrument:** NIFTY index, priced as futures ·
**Tested:** October 2026 · **Verdict:** failed, closed for good

## Idea

Trade the 9/20 exponential moving-average cross on 15-minute closes, intraday.

## Rules

EMAs continuous across days; enter at the close of the crossing candle; exit on the opposite cross
or late in the day. Variants fixed before the first run: skip the opening cross, an earlier entry
cut-off, pullback entries, first three crosses only, a minimum separation, a fixed 0.3% stop.

## Protocol and result, in three rounds

1. **Tuning, P1+P2 (2015-2019), 993 trades.** Gross +0.046% a trade, +0.048% over a drift control
   (t 3.0): a real but small signal, about the cost of a futures round trip. An independent rebuild
   from the raw data matched every figure.
2. **Frozen hold-out, P3+P4 (2019-2024), 1,034 trades.** Primary rule (base + 0.3% stop, 0.03%
   futures cost): +0.016% a trade, t 1.04, and about zero without the five best days. **Failed.**
   The signal itself replicated (t 2.9); the stop that had lifted in-sample t to 2.45 *lowered* it
   out of sample.
3. **A full re-tune on P1-P4** (1,013 variants, any timeframe, 20+ features, stops, targets,
   trails). Candidate t 4.0 in sample, positive in all four leave-one-period-out folds. Pass bar
   written and hashed, then **P5 (2024-2026), 140 trades: -0.049% a trade, t -1.42, every year
   negative.** Failed all three conditions.

## What I learned

- Leave-one-period-out inside the tuning data is not a hold-out: the candidate passed it 4 of 4
  times and then failed the untouched segment outright.
- No filter removed a losing subset in all four tuning segments (0 of 300), and no exit helped all
  four: filters concentrate trades, they do not remove bad ones.
- The signal itself weakened in the low-volatility 2024-26 market. All five segments are now spent
  for intraday EMA-cross trend-following on NIFTY.
