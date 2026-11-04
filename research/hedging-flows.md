# Option-seller hedging flows

**Source:** my own question (a market story) · **Instrument:** NIFTY index; 96 stocks ·
**Tested:** October 2026 · **Verdict:** real, too small to trade

## Idea

Option sellers who are short gamma buy futures into rises and sell into falls, so moves should
continue, most of all late in the day and on expiry day. A counting study, not a strategy.

## Protocol

NIFTY 2021-2024 (one lab window), Budget days out, gross moves. Then the same question on 96
stocks, 2015-2024: after a 1-2% move from yesterday's close or today's open, does the move continue?

## Result

- **Last half hour:** the day's direction continues by +0.016% (t 2.37, 54% of days), against a
  0.08% futures cost, and fading year by year (+0.022%, +0.032%, +0.009%, +0.002%).
- **Expiry day is not stronger** (+0.026%, t 1.79). On expiry days that had already moved a lot,
  the last leg reversed.
- **Fast moves** (0.25-0.5% in 15-30 minutes): the next 30-60 minutes are a coin toss.
- **Stocks:** twelve versions of "follow a 1-2% move": next 30-60 minutes about zero; held to the
  close at most +0.06% before a 0.08-0.12% cost.

## What I learned

The mechanism is real, and on NIFTY it is one or two hundredths of a percent. A true dealer-
positioning gauge from open interest was not tested.
