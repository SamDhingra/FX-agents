# Failed-breakout reversal (gold) — author's v1.0 spec, functions verbatim

06:00–08:00 NY range, 5m failed break back inside below the midpoint in a choppy 15m market (ER ≤ 0.30), entry at the next 3-minute boundary, target the range midpoint, stop beyond the signal candle, out 11:30 NY. Real OANDA bid/ask; R after spread and OANDA Canada's 1% CAD conversion. **Step 1:** 2021 → Sep 2026 must clear every gate combined and be positive in each set. **Step 2:** only then is untouched 2016–2020 opened, once.

### holdout_m1 — seen (step 1): **no pass**

| Test | Trades | Win | Avg R | 95% range | 1.5× costs | 2× costs | 1st half | 2nd half | Total R | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 6 | 17% | -0.158 | -1.00 to +1.53 | -0.204 | -0.250 | -1.000 | +4.053 | -0.9 | 7 min |
| coin-flip control | 6 | 50% | +0.729 | -1.00 to +2.47 | +0.683 | +0.637 | +0.064 | +4.053 | +4.4 | 8 min |
| boundary control | 36 | 31% | +0.014 | -0.47 to +0.54 | -0.040 | -0.093 | -0.079 | +0.339 | +0.5 | 9 min |

Signal funnel: days with 0600 0800 range 967 → 5m breach and close inside below mid 4,189 → prev 5m closed inside range 2,368 → er15 le 030 1,527 → news and 3m open valid 1,480 → not invalidated before 3m open 1,268 → pass cost to stop le 020 412 → pass net rr ge 150 7 → first qualifying trade of day 6
Exits: stop 83%, midpoint_target 17%. Long +0.263 (4), short -1.000 (2). Typical stop $2.75 (middle half $2.25–$3.59); spread 10% of it.

### dev_m1 — seen (step 1): **no pass**

| Test | Trades | Win | Avg R | 95% range | 1.5× costs | 2× costs | 1st half | 2nd half | Total R | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 26 | 31% | -0.053 | -0.69 to +0.66 | -0.101 | -0.148 | +0.618 | -0.176 | -1.4 | 9 min |
| coin-flip control | 26 | 42% | +0.341 | -0.28 to +0.99 | +0.294 | +0.247 | +0.492 | +0.314 | +8.9 | 8 min |
| boundary control | 62 | 29% | -0.081 | -0.45 to +0.29 | -0.130 | -0.178 | +0.749 | -0.204 | -5.0 | 8 min |

Signal funnel: days with 0600 0800 range 516 → 5m breach and close inside below mid 2,121 → prev 5m closed inside range 1,229 → er15 le 030 826 → news and 3m open valid 797 → not invalidated before 3m open 704 → pass cost to stop le 020 287 → pass net rr ge 150 32 → first qualifying trade of day 26
Exits: stop 69%, midpoint_target 23%, flat_1130 8%. Long -0.700 (11), short +0.421 (15). Typical stop $6.02 (middle half $4.36–$7.43); spread 10% of it.

### seen, combined — step 1 gate: **no pass**

| Test | Trades | Win | Avg R | 95% range | 1.5× costs | 2× costs | 1st half | 2nd half | Total R | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 32 | 28% | -0.073 | -0.62 to +0.57 | -0.120 | -0.167 | -1.000 | +0.099 | -2.3 | 9 min |
| coin-flip control | 32 | 44% | +0.414 | -0.15 to +1.02 | +0.367 | +0.320 | +0.064 | +0.479 | +13.2 | 8 min |
| boundary control | 98 | 30% | -0.046 | -0.34 to +0.26 | -0.097 | -0.147 | -0.047 | -0.046 | -4.5 | 8 min |

**Step 1 failed — old_m1 was NOT opened** and stays untouched.

