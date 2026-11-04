# First-candle colour to credit spread

**Source:** my own · **Instrument:** NIFTY weekly option spreads · **Tested:** October 2026 ·
**Verdict:** failed, closed

## Idea

If the first five-minute candle is green, sell a bull put spread; if red, a bear call spread.
Enter at 09:21, exit the same day.

## Rules

Sell 100 points out of the money and buy 300 out (also tested: sell ATM, buy 200 out); stop at 5%
of margin, target at 15% of margin. A grid around them: 2 sold strikes x 4 widths x 6 exit times x
7 stops x 10 targets = 3,360 settings.

## Protocol

Tuned on option segments P2+P3 (October 2021 to April 2024). A luck check on the same days: the
opposite colour, always bullish, always bearish, and 300 coin-toss direction series.

## Result

- My rules as stated: about **-Rs 360 a trade** for one lot (t -4.7), before costs +Rs 30-50.
- **0 of 3,360 settings profitable after costs**, in all four day sets (with and without expiry
  days, with and without tiny first candles). Four orders cost about Rs 400 a trade.
- The colour's best setting was beaten by 60-76% of the coin-toss series, and the *opposite*
  colour did better than the colour.
- A 15%-of-margin target (63-109 points) is larger than the credit collected (24-83 points), so it
  almost never fires.

## What I learned

A spread only reshapes the payoff of its direction call; it cannot add an edge the call does not
have. Any same-day two-leg option idea starts about Rs 400 a lot behind, so ask first what pays
for that. The sealed segments were never opened: there was no rule worth a hold-out.
