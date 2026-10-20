# ndq_orb_vwap_v1 — NAS100 09:30–09:45 opening-range breakout + cash VWAP (author's pre-registered spec)

Author's constants and strategy functions used verbatim (fxagents/ndq_orb.py) with four recorded fixes that bring the code in line with the written spec, frozen 2026-10-20 before any run. Real OANDA bid/ask fills, 0.15 × spread stop slippage, OANDA Canada 1% CAD conversion; R after costs; 2× costs pays one more spread; exact coin-flip control (long and short averaged at the same minute). **Step 1:** seen data 2021 → Sep 2026 must clear every gate combined and be positive in each set. **Step 2:** only then is the untouched 2016–2020 export opened, once, and judged.

### holdout_m1 — seen (step 1): **no pass**

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 47 | 43% | +0.103 | -0.31 to +0.52 | +0.089 | +0.265 | -0.098 | +4.8 | +431 | 107 min |
| exact coin-flip control | 47 | 40% | -0.063 | -0.28 to +0.16 | -0.077 | +0.003 | -0.144 | -2.9 | -14 | 107 min |
| no 1H/15m bias | 86 | 43% | +0.214 | -0.11 to +0.54 | +0.199 | +0.347 | +0.061 | +18.4 | +1,182 | 86 min |

Exits: stop 57%, target 15%, trail_stop 15%, flat_1555 13%. Long +0.179 (31), short -0.043 (16). Typical stop 43.0 pts (middle half 35.2–57.5 pts); typical spread 1% of it.

### dev_m1 — seen (step 1): **no pass**

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 32 | 25% | -0.566 | -0.82 to -0.29 | -0.582 | -0.633 | -0.506 | -18.1 | -1,291 | 53 min |
| exact coin-flip control | 32 | 25% | -0.367 | -0.57 to -0.13 | -0.383 | -0.366 | -0.367 | -11.7 | -947 | 53 min |
| no 1H/15m bias | 67 | 36% | -0.145 | -0.44 to +0.19 | -0.162 | -0.263 | -0.037 | -9.7 | -864 | 74 min |

Exits: stop 75%, trail_stop 16%, flat_1555 6%, closure 3%. Long -0.595 (23), short -0.491 (9). Typical stop 66.4 pts (middle half 51.9–88.4 pts); typical spread 1% of it.

### seen, combined — step 1 gate: **no pass**

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 79 | 35% | -0.168 | -0.44 to +0.13 | -0.183 | +0.187 | -0.465 | -13.3 | -859 | 94 min |
| exact coin-flip control | 79 | 34% | -0.186 | -0.35 to -0.02 | -0.201 | -0.068 | -0.284 | -14.7 | -960 | 94 min |
| no 1H/15m bias | 153 | 40% | +0.057 | -0.16 to +0.29 | +0.041 | +0.252 | -0.080 | +8.7 | +318 | 81 min |

**Step 1 failed — old_m1_idx_NDQ was NOT opened** and stays untouched.

