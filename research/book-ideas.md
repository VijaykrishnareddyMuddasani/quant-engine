# Ideas from trading books

**Source:** a list of intraday ideas distilled from 30 trading books · **Instrument:** 96 NSE stocks,
NIFTY · **Tested:** September-October 2026 · **Verdict:** four failed, two skipped

## Protocol

Each idea was tested in list order. Development data 2015-2024 (one-minute bars, 96 liquid stocks;
survivor-selected, which flatters long-only results); 2025 onwards sealed. Each idea got a written
pre-registration, hashed before the run, with a kill bar taken from the source's own claims.

## Results

**Lead-lag catch-up (sector leaders, then their followers).** All 14 trials below the 14 bps bar;
the best +1.1 bps. Followers move together with the leader, in the same minutes: by the time the
signal fires, about 45% of the follower's move has already happened. The sector effect is real
(t 5, beats every control) but about 1 bp, and only in IT and pharma.

**Relative strength against NIFTY.** 0 of 16 trials pass. Ranked mid-morning, the strongest stocks
give back 3-6 bps; ranked in the afternoon they add +2.5 bps (t 4.2) against a 22 bps bar.

**Cross-sectional overnight reversal.** The premise is large at the auction open (+20 to +55 bps a
day on a broad universe) but almost all of it is gone within the first minute of trading: +21.5 bps
at the auction open, +7.8 at the first minute's price, +4.7 five minutes later, and about zero at the
first minute since 2021. Not tradable at a price one can actually get.

**Fading levels (round numbers, the morning's high and low, yesterday's point of control).** These
levels hold no more often than randomly shifted prices; round numbers hold *less* often (53% against
57%, z -3.6). Fade returns -0.8 to +0.2 bps against an 8 bps bar.

**Event drift and spike fades on central-bank and Budget days.** Skipped: 15-40 trades in ten years
is too few to trade or to test.

## What I learned

Several book claims describe something real that is too small, or that happens at a price no order
can get (the auction open). Measure where the effect lives in time before designing an entry.
