# vol_breakout_v1 — gold 5m compression breakout with the 15m + 1H trend (author's pre-registered spec)

Author's constants and strategy functions used verbatim (fxagents/vol_breakout.py), frozen 2026-10-19 before any run. Real OANDA bid/ask fills; R after spread; 2× costs pays one more spread. **Step 1:** seen data 2021 → Sep 2026 must clear every gate combined and be positive in each set. **Step 2:** only then is the untouched 2016–2020 export opened, once, and judged.

### dev_m1 — seen (step 1): **no pass**

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 220 | 38% | -0.122 | -0.30 to +0.05 | -0.193 | -0.003 | -0.226 | -26.8 | -5,168 | 46 min |
| coin-flip control | 220 | 39% | -0.088 | -0.27 to +0.08 | -0.159 | -0.134 | -0.047 | -19.3 | +2,025 | 56 min |
| no HTF bias | 293 | 38% | -0.135 | -0.29 to +0.02 | -0.208 | -0.007 | -0.254 | -39.6 | -7,778 | 46 min |

Exits: stop 57%, be_stop 15%, target 15%, flat_1630 12%. Long -0.168 (136), short -0.046 (84). Typical stop $9.29 (middle half $6.38–$14.02); typical spread 7% of it.

### holdout_m1 — seen (step 1): **no pass**

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 309 | 40% | -0.143 | -0.28 to -0.00 | -0.227 | -0.110 | -0.182 | -44.2 | -1,230 | 45 min |
| coin-flip control | 309 | 42% | -0.067 | -0.22 to +0.09 | -0.150 | -0.111 | -0.017 | -20.7 | -1,405 | 44 min |
| no HTF bias | 431 | 40% | -0.114 | -0.23 to +0.01 | -0.201 | -0.131 | -0.096 | -49.3 | -994 | 45 min |

Exits: stop 56%, be_stop 18%, target 13%, flat_1630 12%. Long -0.136 (166), short -0.151 (143). Typical stop $3.78 (middle half $3.00–$4.81); typical spread 8% of it.

### seen, combined — step 1 gate: **no pass**

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 529 | 39% | -0.134 | -0.24 to -0.03 | -0.212 | -0.115 | -0.150 | -71.0 | -6,398 | 45 min |
| coin-flip control | 529 | 41% | -0.076 | -0.19 to +0.04 | -0.154 | -0.061 | -0.087 | -40.0 | +620 | 47 min |
| no HTF bias | 724 | 40% | -0.123 | -0.22 to -0.03 | -0.204 | -0.099 | -0.143 | -88.9 | -8,772 | 45 min |

**Step 1 failed — old_m1 was NOT opened** and stays untouched.

