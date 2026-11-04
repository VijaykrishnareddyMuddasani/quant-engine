# Research log

Ideas I tested on Indian index, option and stock data between September and November 2026, and
closed. Some are my own; others came from books, a course, a friend, published papers and paid
products, and are credited as such and described in my own words. Every one of them failed, or
was not worth its costs. The point of this log is the method: how each idea was given a fair
chance, and how it was stopped.

My live strategies are not here.

## Protocol

The protocol is implemented in [`quant_engine.validation`](../src/quant_engine/validation) and
demonstrated end to end in [`examples/research_protocol.py`](../examples/research_protocol.py).

1. **Restate the rules before coding them**, and test an ambiguous wording both ways rather than
   pick the one that looks better. Thresholds are in % of the index, never in points.
2. **Cut history into chronological segments** (P1-P5) and tune on some only. For the option data
   (Aug 2020 to Sep 2026, 1,510 sessions) the segments are 302 sessions each; for index minute data
   (2015 onwards) about 580.
3. **Count every trial** and compare the best result with the best result of the same search on
   edge-free data (random levels, coin-toss directions, sign-flipped trades, shifted dates).
4. **Pre-register the hold-out**: the rule, the pass bar and a SHA-256 hash of the code are written
   down before the sealed segment is opened, once. A failed hold-out closes the idea; the segment
   is spent for that family.
5. **Price options on recorded premiums** (Dhan minute data), with brokerage, statutory charges and
   slippage, and say where a model price had to stand in.
6. **Leave out Union Budget days**, which I would not trade.

## Index

| Idea | Source | Instrument | Verdict |
| --- | --- | --- | --- |
| [Strict intraday short straddle](intraday-short-straddle.md) | own | NIFTY weekly options | Failed on randomly drawn segments: -Rs 1,383 a trade (4 lots), t -2.8 |
| [Intraday straddles, sold and bought](intraday-straddles.md) | own | NIFTY weekly options | No edge either way; frozen expiry-day rule weak out of sample (t 0.78) |
| [First-candle colour to credit spread](first-candle-colour-spread.md) | own | NIFTY option spreads | 0 of 3,360 settings profitable; colour worse than a coin toss |
| [EMA 9/20 crossover](ema-crossover.md) | own | NIFTY index / futures | Tuned candidate (t 4.0) failed the last sealed segment (t -1.4) |
| [5-EMA reversal](five-ema-reversal.md) | own | NIFTY index | Best of 6,144 variants inside the luck benchmark |
| [Option-seller hedging flows](hedging-flows.md) | own | NIFTY index, 96 stocks | Real but 1-6 bps, below costs |
| [Volume-profile swing breakouts](volume-profile-swing.md) | own | 5 large-cap stocks | No excess over drift (t -1.0) |
| [Hourly trend system](friend-trend-system.md) | a friend's report | NIFTY options | -Rs 31 a trade, t -0.26; 23 variants, nothing |
| [Central Pivot Range setups](cpr-setups.md) | a paid course | NIFTY index, 95 stocks | CPR width does not predict trend days; every frozen rule failed |
| [Ideas from trading books](book-ideas.md) | 30 trading books | stocks, NIFTY | Four failed their pre-registered bars; two skipped (too few trades) |
| [20+ online intraday stock strategies](online-stock-strategies.md) | websites | 5 large-cap stocks | Final frozen run +2 to +4 bps after costs, t 0.2-0.4 |
| [Swing rules on NIFTY futures](swing-futures.md) | textbook rules | NIFTY futures | Best rule t 1.2 out of sample; carry eats half of buy-and-hold |
| [Gann square-of-nine indicator](gann-indicator.md) | a paid indicator | NIFTY index | Real levels did worse than randomly shifted ones |
| [Overnight credit-spread algo](credit-spread-rebuild.md) | a commercial algo | NIFTY option spreads | Rebuilt rule: -Rs 122 a trade; failed its frozen run |
| [Stocks in play](stocks-in-play.md) | Zarattini, Barbon and Aziz (2024) | NIFTY 200 stocks | Strong in design, failed the sealed 2025-26 run (t 0.75) |
| [Fibonacci levels on the first candle](fibonacci-first-candle.md) | a chart shared with me | NIFTY options | Target hits at random-walk rates; every family lost |

## What the failures taught

- **Costs decide most intraday ideas.** A same-day two-leg option trade starts about Rs 400 a lot
  behind; a four-leg one twice that. Several ideas here had a real gross edge that costs ate.
- **The best of a search is not an edge.** Random levels, coin-toss directions and the same search
  on older data are the control. Two Gann tests, the colour spread and the 5-EMA grid all lost to
  their own controls.
- **Leave-one-period-out inside the tuning data is not a hold-out.** The EMA candidate passed it
  four out of four times and then failed the sealed segment outright.
- **Fills matter as much as signals.** Filling one minute later halved the stocks-in-play edge.
- **Model prices lie exactly where it hurts.** Hedge legs that left the downloaded strike window lost
  their prices and were the losing legs; filling them from a model first inflated a result by about
  Rs 390 a trade. Put-call parity could not rebuild a missing leg either.
- **Look-ahead hides in candle timing.** One online rule read the colour of a candle that had not
  closed yet; its results were thrown away and every rule's timing was re-checked.
- **A track record earned in a falling market is a direction bet.** All the profit of the published
  credit-spread algo came from its bearish side while NIFTY fell 12%.
