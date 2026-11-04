# 20+ online intraday stock strategies

**Source:** strategies published on websites claiming to work intraday on Indian stocks ·
**Instrument:** ICICI Bank, Reliance, L&T, Infosys, SBI (cash) · **Tested:** September 2026 ·
**Verdict:** failed after costs

## Protocol

1. Collect at least 20 strategies with their exact published rules (a catalogue was written first).
2. Test and tune every one on a **single stock**, design years 2015-2021, check 2022-2024.
3. Refine the survivors on a **second stock**.
4. One **frozen run** on the remaining **three stocks**, no re-tuning afterwards.

Every trial was counted; 2025 onwards stayed sealed. The five stocks share the same market days, so
the three-stock check is weaker than three independent tests.

## Result

- Most rules lost before costs on the first stock. Two families survived to the final run.
- Final frozen run on SBI, L&T and Infosys, 2015-2024: gross +10.5 and +12.2 bps a trade, real and
  better than luck. After costs for a Rs 1 lakh position: **+2.2 and +3.9 bps (day-level t 0.2 and
  0.4)**, and negative at a stress cost.

## What I learned

- One published rule entered on the colour of a candle that had not finished yet: a look-ahead. Its
  results were discarded, and the candle timing of every other rule was checked again.
- Intraday costs on cash equities (4.5-12 bps a round trip) are larger than most published edges.
