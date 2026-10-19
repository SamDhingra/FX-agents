# h4_donchian_trend_v1 — gold 4H Donchian breakout + EMA200 trend + chandelier trail (author's pre-registered spec)

Author's constants and strategy functions used verbatim (fxagents/h4_donchian.py; one recorded fix: overnight financing is charged on every 17:00 NY crossing), frozen 2026-10-19 before any run. Real OANDA bid/ask fills; R after spread and overnight financing; 2× costs doubles both. **Step 1:** seen data 2021 → Sep 2026 must clear every gate combined and be positive in each set. **Step 2:** only then is the untouched 2016–2020 export opened, once, and judged.

### dev_m1 — seen (step 1): **no pass**

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 46 | 50% | +0.081 | -0.18 to +0.36 | +0.030 | +0.356 | -0.277 | +3.7 | -1,173 | 1843 min |
| coin-flip control | 46 | 37% | -0.134 | -0.39 to +0.13 | -0.177 | -0.158 | -0.103 | -6.2 | -3,391 | 1341 min |
| no 4H EMA200 bias | 64 | 48% | +0.033 | -0.20 to +0.29 | -0.015 | +0.193 | -0.159 | +2.1 | -1,296 | 1890 min |

Exits: chandelier_trail 46%, fri_flat 35%, stop 20%. Held overnight: 78%; rollovers charged: 97 (avg financing 0.036R per trade). Long +0.391 (28), short -0.402 (18). Typical stop $47.38 (middle half $34.99–$58.50); typical total cost (spread + financing) 4.4% of it; median hold 30.7 h.

### holdout_m1 — seen (step 1): **no pass**

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 38 | 26% | -0.387 | -0.65 to -0.08 | -0.444 | -0.369 | -0.399 | -14.7 | -1,919 | 1196 min |
| coin-flip control | 38 | 47% | +0.056 | -0.27 to +0.43 | -0.015 | +0.284 | -0.092 | +2.1 | +112 | 1649 min |
| no 4H EMA200 bias | 59 | 27% | -0.310 | -0.55 to -0.02 | -0.367 | -0.212 | -0.377 | -18.3 | -2,708 | 1097 min |

Exits: stop 47%, fri_flat 32%, chandelier_trail 18%, closure 3%. Held overnight: 58%; rollovers charged: 54 (avg financing 0.034R per trade). Long -0.281 (24), short -0.570 (14). Typical stop $14.02 (middle half $10.94–$17.12); typical total cost (spread + financing) 3.9% of it; median hold 19.9 h.

### seen, combined — step 1 gate: **no pass**

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 84 | 39% | -0.131 | -0.33 to +0.09 | -0.184 | -0.281 | -0.056 | -11.0 | -3,092 | 1554 min |
| coin-flip control | 84 | 42% | -0.048 | -0.25 to +0.17 | -0.103 | -0.054 | -0.045 | -4.0 | -3,279 | 1480 min |
| no 4H EMA200 bias | 123 | 38% | -0.131 | -0.30 to +0.06 | -0.184 | -0.193 | -0.094 | -16.1 | -4,004 | 1650 min |

**Step 1 failed — old_m1 was NOT opened** and stays untouched.

