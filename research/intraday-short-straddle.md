# Strict intraday short straddle

**Source:** my own · **Instrument:** NIFTY nearest-weekly options · **Tested:** October 2026 ·
**Verdict:** failed

## Idea

Sell the at-the-money straddle one minute after the open with tight, mechanical risk rules, and
collect the intraday decay.

## Rules (frozen before the test)

- Every session except expiry day. Sell the ATM call and put at 09:16.
- Each leg has its own stop 50% above its sale price; the other leg keeps its original stop.
- Buy a wing on each side costing at most 5% of that side's sold option, held to the exit.
- Everything closed at 14:28. Four lots. Costs: 1 point of slippage per sold order, 0.5 per wing.

## Protocol

The 1,510 option sessions were cut into five 302-session segments. Before anything ran, two
segments were drawn at random with a recorded seed: **P2 and P3**. The other three stayed closed.

## Result: 474 trades, about 194 a year

- **After costs: -Rs 1,383 a trade, t -2.8**, -Rs 2.68 lakh a year, worst drawdown Rs 7.33 lakh.
  Both segments negative (P2 -1,769, P3 -997).
- Before costs: +Rs 1,108 a trade (t 2.2). Eight orders a day cost Rs 2,491.
- 39% of days no stop (+2,243), 59% one stop (-2,948), 7 days both stops (-35,651 on average).
- Every VIX band negative; every exit time from 10:30 to the late afternoon negative.
- Without wings +Rs 217 (t 0.5); without stops -Rs 2,354. Break-even needs about 0.3 points of
  slippage per sold order, which is not achievable at the touch.

Follow-ups on the same segments, both worse: a profit target at 0.5-5% of margin (caps the
winners while stop days stay full size), and a grid of 4,662 long-straddle variants (0 profitable
after costs).

## What I learned

The gross edge is real but smaller than the cost of eight orders. Stops are close to a coin flip
per stop, but they cut the fat tail, so removing them is worse. More exits cannot create an edge
that is not there.
