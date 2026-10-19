# Playbook two-step test — 18 setups as the bot trades them (frozen a2b43a134c89, playbook as of 2026-10-17)

Each cell replayed by the playbook's own research engine (live filters + live position manager on 1-minute bars) on OANDA bid/ask data with the **real spread of every minute**; one trade at a time per cell. R after spread; 2× costs pays one more spread. The playbook was picked on Oct 2025 → Oct 2026, so that piece is in-sample and only shown.

**Step 1 (2021 → Sep 2026):** ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, and positive in each clean piece. {len(cells)} cells at once → about 1 could pass by luck. **Step 2:** passers only, once, on untouched 2016–2020.

## Step 1 — 2021 → Sep 2026

| Cell | Step 1 | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Spread / risk | 2021 → Sep 2024 (clean) | Oct 2024 → Oct 7 2025 (clean) | Oct 8 2025 → Sep 2026 (picked here) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dtfx_wick_fib:5m@pb-ndq-4a8c-scalp | **no** | 728 | 45% | -0.076 | -0.13 to -0.02 | -0.152 | -0.059 | -0.094 | 6% | -0.088 (486) | -0.086 (128) | -0.016 (114) |
| dtfx_wick_fib:15m@pb-ndq-b988 | **no** | 919 | 48% | -0.042 | -0.10 to +0.01 | -0.084 | -0.007 | -0.077 | 3% | -0.036 (614) | -0.125 (160) | +0.021 (145) |
| smt_divergence:15m@pb-ndq-06e2-trend | **no** | 731 | 38% | -0.011 | -0.11 to +0.08 | -0.074 | +0.038 | -0.060 | 5% | -0.021 (493) | +0.050 (130) | -0.038 (108) |
| macd_cross:5m@pb-ndq-d | **no** | 1134 | 53% | +0.052 | -0.00 to +0.11 | -0.013 | +0.090 | +0.014 | 5% | +0.035 (771) | +0.083 (191) | +0.091 (172) |
| dtfx_close_fib:15m@pb-us30-b988-trend | **no** | 764 | 36% | -0.089 | -0.18 to -0.00 | -0.117 | -0.114 | -0.064 | 2% | -0.078 (508) | -0.018 (122) | -0.198 (134) |
| sr_rejection:30m@pb-us30-d-trend | **no** | 685 | 35% | -0.059 | -0.16 to +0.05 | -0.102 | -0.077 | -0.041 | 4% | -0.024 (457) | -0.383 (105) | +0.086 (123) |
| ict_amd:3m@pb-us30-013f | **no** | 937 | 45% | -0.118 | -0.18 to -0.05 | -0.169 | -0.129 | -0.108 | 4% | -0.134 (614) | -0.087 (167) | -0.089 (156) |
| dtfx_close_fib:15m@pb-us30-b988 | **no** | 789 | 45% | -0.096 | -0.16 to -0.03 | -0.124 | -0.103 | -0.088 | 2% | -0.095 (525) | -0.070 (126) | -0.121 (138) |
| smc_mss:3m@pb-xau-d | **no** | 1083 | 45% | -0.110 | -0.16 to -0.05 | -0.201 | -0.079 | -0.141 | 8% | -0.104 (747) | -0.106 (171) | -0.138 (165) |
| dtfx_wick_fib:3m@pb-xau-2ca4 | **no** | 730 | 45% | -0.119 | -0.19 to -0.04 | -0.243 | -0.146 | -0.093 | 10% | -0.132 (482) | -0.172 (119) | -0.025 (129) |
| smc_displacement:3m@pb-xau-d | **no** | 1278 | 42% | -0.181 | -0.24 to -0.12 | -0.380 | -0.270 | -0.092 | 17% | -0.222 (869) | -0.180 (188) | -0.021 (221) |
| dtfx_close_fib:3m@pb-xau-4a8c | **no** | 790 | 45% | -0.085 | -0.16 to -0.01 | -0.209 | -0.197 | +0.027 | 11% | -0.143 (511) | -0.089 (129) | +0.115 (150) |
| ict_turtle_soup:15m@pb-xau-6062 | **no** | 922 | 45% | -0.136 | -0.20 to -0.07 | -0.238 | -0.132 | -0.139 | 8% | -0.119 (647) | -0.256 (150) | -0.078 (125) |
| ict_turtle_soup:15m@pb-xau-6062-trend | **no** | 922 | 35% | -0.115 | -0.19 to -0.03 | -0.218 | -0.117 | -0.113 | 8% | -0.102 (647) | -0.240 (150) | -0.034 (125) |
| smc_bos_retest:5m@pb-xau-392f | **no** | 1671 | 47% | -0.079 | -0.13 to -0.03 | -0.167 | -0.139 | -0.019 | 8% | -0.124 (1099) | -0.028 (280) | +0.044 (292) |
| ict_turtle_soup:5m@pb-xau-285e | **no** | 780 | 47% | -0.080 | -0.14 to -0.02 | -0.147 | -0.040 | -0.120 | 6% | -0.064 (528) | -0.172 (138) | -0.043 (114) |
| ict_2022:3m@pb-xau-504f | **no** | 781 | 43% | -0.147 | -0.22 to -0.08 | -0.261 | -0.177 | -0.117 | 10% | -0.156 (511) | -0.191 (135) | -0.069 (135) |
| dtfx_close_fib:3m@pb-xau-4a8c-scalp | **no** | 812 | 43% | -0.116 | -0.17 to -0.07 | -0.241 | -0.162 | -0.071 | 11% | -0.151 (524) | -0.159 (133) | +0.036 (155) |

**0 of 18 cells pass step 1.**

Nothing passed step 1, so the 2016–2020 data was not opened.

