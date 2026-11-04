# Stocks in play

**Source:** Zarattini, Barbon and Aziz (2024), "A profitable day trading strategy for the U.S.
equity market", adapted to NSE · **Instrument:** NIFTY 200 stocks (cash) · **Tested:** October 2026 ·
**Verdict:** failed the sealed run, closed

## Idea

A stock trading on unusually high volume in the first minutes is "in play": news has arrived and
the move is likelier to continue.

## Rules

Five minutes after the open, rank stocks by relative volume (first five-minute turnover against its
14-session average). Take the top five, each in the direction of its own first candle; enter on a
break of that candle's high or low; stop at its other end; exit late in the day. 8 bps of cost.

## Protocol

- Design on 95 stocks, 2015-2021, 108 settings.
- A frozen run on 2022-2024 on point-in-time NIFTY 200 members (253 stocks, no survivor bias).
- A pre-registered sealed run on 2025 to September 2026, hash written first, with a two-part pass
  bar: mean of two entry variants at 12 bps >= +0.05% a trade, and day-level t >= 1.5 at 8 bps.

## Result

- Design: +0.22% a trade net, t 7.9, positive every year; 94 of 108 settings positive.
- 2022-2024 frozen: **+0.14% a trade (t 2.71)** filled exactly at the breakout level; **+0.046%
  (t 0.77) filled one minute later.** On the original 95 stocks alone it shrank to a fifth.
- Sealed 2025-2026: **failed** (t 0.75).

## What I learned

The edge was real in design and mostly real out of sample, but it lived in the fill. When one
minute of delay halves a result, the backtest is measuring the fill assumption. The honest next step
would have been to measure live fills on paper before any capital.
