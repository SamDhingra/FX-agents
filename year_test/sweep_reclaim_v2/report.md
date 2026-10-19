# sweep_reclaim_v2 — gold 15m sweep → 5m reclaim, ATR-scaled (author's code, frozen Oct 19 2026)

Rules exactly as supplied (fxagents/sweep_reclaim_v2.py). Real OANDA bid/ask fills; R after spread; 2× costs pays one more spread. Gates: ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, better than the coin flip.

**Protocol (fixed before running):** step 1 — the two already-seen sets must clear every gate combined and be positive in each. Step 2 — only then is the untouched 2016–2020 export opened, once, and judged.

| Data | Role | Gates | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Coin flip | Median gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| dev_m1 | seen (step 1) | **no pass** | 188 | 35% | -0.073 | -0.24 to +0.09 | -0.163 | +0.082 | -0.238 | -0.075 | $3,852 |
| holdout_m1 | seen (step 1) | **no pass** | 345 | 32% | -0.134 | -0.27 to -0.00 | -0.243 | -0.115 | -0.156 | -0.036 | $1,877 |
| **seen, combined** | step 1 gate | **no pass** | 533 | 33% | -0.112 | -0.22 to -0.01 | -0.215 | -0.128 | -0.098 | -0.050 |  |

**Step 1 failed — old_m1 was NOT opened** and stays untouched for future ideas.

- dev_m1: exits stop 63%, target 29%, flat_1630 8%, closure 1%; long -0.043 (80), short -0.095 (108); typical stop $7.44, spread 8% of it.
- holdout_m1: exits stop 66%, target 28%, flat_1630 5%; long -0.122 (174), short -0.146 (171); typical stop $3.09, spread 10% of it.
