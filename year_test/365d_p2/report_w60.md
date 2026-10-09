# Strategy test — 365 days · costs oanda · p2

Created 2026-10-09 00:19 NY · trades 2025-10-08 → 2026-10-08 · 1,610,615 simulated trades · 10,590 cells

R is per trade in units of its own risk, after spread. Quarters split the period in four equal parts; an edge worth trading is positive in most quarters, not just on average. 1-minute cells are listed but the playbook doesn't trade 1m (spread is too large a share of the bar).

## 1 · The playbook system, replayed week by week on unseen data

Each week: pick cells from the trailing **60 observed trade days** (days on which the research recorded at least one trade — not calendar days), trade them the next week, capacity rules on. The replay starts 2025-11-05, so its first weeks select on fewer days. Portfolio instruments (config trade: true): XAUUSD, NDQ, US30. This is the number that says whether the approach works.

All R figures in this section are **rw** (budget-weighted: each trade's R × the share of the full risk budget Risk could take).

- trades **1989**, win rate **47%**, avg **-0.017R**, total **-33.82R**, profit factor 0.94, worst drawdown -49.93R, t-stat -1.15, 95% interval of the average R per trade (day-block bootstrap, trading days resampled; not selection-adjusted): [-0.049, +0.014]
- without the 3 best trades: -43.78R
- XAUUSD: 1217 trades, 48% win, -11.33R
- NDQ: 370 trades, 46% win, -17.20R
- US30: 402 trades, 43% win, -5.29R

By month (rw): 2025-11 +0.3 (207) · 2025-12 -16.7 (296) · 2026-01 +2.5 (180) · 2026-02 -5.7 (138) · 2026-03 -0.4 (216) · 2026-04 +9.5 (162) · 2026-05 -0.1 (135) · 2026-06 +3.8 (165) · 2026-07 -22.6 (120) · 2026-08 -5.9 (178) · 2026-09 +0.1 (174) · 2026-10 +1.4 (18)

Positive weeks: 22 of 49 · weekly rw sums to -33.82R (= the total above)

## 2 · Cells that held up (≥30 trades, positive in both halves and ≥3 of 4 quarters)

| setup | variant | sym | tf | exit | trades | win | avg R | t | H1 | H2 | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dtfx_wick_fib | vol=impulse | XAUUSD | 3min | scalp | 64 | 72% | +0.255 | 2.7 | +0.25 | +0.27 | +0.21 | +0.27 | +0.51 | +0.03 |
| rsi_pullback | default | XAUUSD | 15min | std | 80 | 65% | +0.277 | 2.6 | +0.26 | +0.30 | +0.30 | +0.21 | -0.17 | +0.73 |
| rsi_pullback | default | XAUUSD | 15min | trend | 78 | 51% | +0.395 | 2.5 | +0.52 | +0.23 | +0.38 | +0.71 | -0.23 | +0.65 |
| ict_turtle_soup | level=session | US30 | 15min | trend | 62 | 50% | +0.557 | 2.5 | +0.47 | +0.66 | +0.43 | +0.50 | +0.93 | +0.40 |
| ict_amd | manip=ny | NDQ | 3min | scalp | 39 | 67% | +0.184 | 2.5 | +0.22 | +0.14 | +0.11 | +0.46 | +0.18 | +0.09 |
| dtfx_wick_fib | vol=impulse | XAUUSD | 3min | std | 62 | 65% | +0.304 | 2.3 | +0.47 | +0.04 | +0.15 | +0.70 | +0.28 | -0.20 |
| smc_ifvg | default | XAUUSD | 15min | std | 147 | 60% | +0.182 | 2.3 | +0.11 | +0.25 | +0.02 | +0.21 | +0.25 | +0.25 |
| ict_turtle_soup | level=session | US30 | 15min | std | 62 | 58% | +0.397 | 2.3 | +0.50 | +0.28 | +0.52 | +0.48 | +0.59 | -0.01 |
| smc_choch | swing=2 | NDQ | 1h | trend | 38 | 63% | +0.285 | 2.2 | +0.31 | +0.24 | +0.37 | +0.25 | +0.30 | +0.18 |
| dtfx_zone | default | NDQ | 30min | std | 57 | 65% | +0.180 | 2.2 | +0.21 | +0.15 | +0.14 | +0.32 | +0.35 | -0.04 |
| trend_breakout | vol=impulse | US30 | 15min | trend | 32 | 56% | +0.679 | 2.2 | +0.91 | +0.48 | +0.95 | +0.87 | +0.57 | +0.41 |
| dtfx_close_fib | vol=impulse | XAUUSD | 3min | scalp | 45 | 71% | +0.237 | 2.2 | +0.27 | +0.19 | +0.48 | +0.13 | +0.55 | -0.13 |
| trend_breakout | vol=impulse | US30 | 15min | std | 33 | 70% | +0.395 | 2.2 | +0.40 | +0.39 | +0.51 | +0.31 | +0.46 | +0.34 |
| vwap | vol=dry | XAUUSD | 15min | std | 83 | 59% | +0.274 | 2.2 | +0.21 | +0.33 | +0.09 | +0.32 | +0.46 | +0.22 |
| dtfx_wick_fib | swing=pb | XAUUSD | 3min | std | 208 | 57% | +0.157 | 2.1 | +0.15 | +0.16 | -0.00 | +0.26 | +0.22 | +0.10 |
| dtfx_close_fib_brk | vol=impulse | US30 | 1min | std | 101 | 61% | +0.213 | 2.0 | +0.19 | +0.24 | -0.06 | +0.45 | +0.21 | +0.25 |
| smc_choch | swing=2 | NDQ | 1h | std | 38 | 63% | +0.165 | 2.0 | +0.25 | +0.05 | +0.17 | +0.35 | +0.04 | +0.06 |
| dtfx_close_fib | mtf=1h | NDQ | 5min | scalp | 55 | 65% | +0.147 | 1.9 | +0.26 | +0.03 | +0.39 | +0.13 | +0.02 | +0.03 |
| dtfx_close_fib_brk | sessions=killzones | XAUUSD | 1min | std | 182 | 57% | +0.158 | 1.9 | +0.19 | +0.13 | +0.21 | +0.18 | +0.24 | -0.02 |
| smc_displacement | swing=3 | XAUUSD | 15min | std | 40 | 65% | +0.284 | 1.8 | +0.43 | +0.07 | +0.31 | +0.87 | +0.21 | -0.02 |
| smc_bos_retest | tol_atr=0.15 | EURUSD | 1h | trend | 33 | 58% | +0.254 | 1.8 | +0.16 | +0.32 | +0.14 | +0.16 | +0.21 | +0.39 |
| smc_displacement | disp_k=1.0 | XAUUSD | 15min | std | 59 | 61% | +0.227 | 1.8 | +0.32 | +0.11 | +0.29 | +0.37 | +0.12 | +0.09 |
| dtfx_wick_fib | swing=5 | NDQ | 3min | scalp | 132 | 64% | +0.119 | 1.8 | +0.20 | +0.03 | +0.16 | +0.25 | +0.13 | -0.07 |
| smc_displacement | swing=3 | XAUUSD | 15min | trend | 39 | 49% | +0.397 | 1.8 | +0.66 | +0.01 | +0.56 | +1.05 | -0.16 | +0.12 |
| smc_displacement | default | XAUUSD | 15min | std | 42 | 64% | +0.273 | 1.8 | +0.48 | +0.00 | +0.34 | +0.89 | +0.03 | -0.02 |
| vwap | vol=dry | XAUUSD | 15min | trend | 80 | 44% | +0.302 | 1.8 | +0.17 | +0.44 | +0.13 | +0.21 | +0.65 | +0.26 |
| ict_turtle_soup | level=session | US30 | 30min | trend | 76 | 47% | +0.314 | 1.8 | +0.41 | +0.24 | +0.30 | +0.51 | -0.12 | +0.56 |
| dtfx_close_fib_brk | vol=impulse | US30 | 1min | scalp | 102 | 60% | +0.164 | 1.7 | +0.17 | +0.16 | +0.03 | +0.32 | +0.19 | +0.14 |
| smc_bos_retest | default | EURUSD | 1h | trend | 33 | 55% | +0.239 | 1.7 | +0.13 | +0.33 | +0.14 | +0.13 | +0.21 | +0.40 |
| trend_breakout | stop_atr=1.0 | NDQ | 1h | std | 50 | 64% | +0.206 | 1.7 | +0.19 | +0.22 | +0.36 | -0.05 | +0.17 | +0.28 |
| dtfx_close_fib | swing=pb | XAUUSD | 3min | std | 155 | 56% | +0.141 | 1.7 | +0.10 | +0.20 | -0.05 | +0.21 | +0.18 | +0.21 |
| dtfx_close_fib | swing=5 | XAUUSD | 5min | std | 60 | 67% | +0.190 | 1.7 | +0.11 | +0.30 | -0.07 | +0.24 | +0.57 | +0.08 |
| ict_turtle_soup | confirm=choch | NDQ | 15min | trend | 56 | 54% | +0.287 | 1.7 | +0.07 | +0.44 | -0.32 | +0.50 | +0.47 | +0.39 |
| dtfx_close_origin | swing=pb | XAUUSD | 3min | std | 125 | 58% | +0.153 | 1.7 | +0.27 | +0.04 | +0.28 | +0.26 | -0.11 | +0.17 |
| dtfx_close_origin | vol=impulse | US30 | 1min | std | 100 | 56% | +0.199 | 1.7 | +0.18 | +0.22 | +0.13 | +0.23 | +0.13 | +0.29 |
| smt_divergence | confirm=reclaim | US30 | 1h | std | 41 | 63% | +0.270 | 1.6 | +0.38 | +0.20 | +0.43 | +0.26 | +0.04 | +0.41 |
| smc_choch | swing=5 | XAUUSD | 15min | std | 85 | 52% | +0.120 | 1.6 | +0.06 | +0.18 | +0.01 | +0.09 | +0.31 | +0.04 |
| ict_amd | manip=ny | NDQ | 3min | std | 39 | 51% | +0.219 | 1.6 | +0.33 | +0.07 | +0.24 | +0.53 | +0.13 | +0.00 |
| ict_amd | manip=ny | NDQ | 1min | scalp | 43 | 67% | +0.134 | 1.6 | +0.02 | +0.32 | -0.07 | +0.20 | +0.34 | +0.30 |
| trend_breakout | default | XAUUSD | 30min | std | 81 | 57% | +0.172 | 1.6 | +0.36 | +0.03 | +0.49 | +0.24 | +0.22 | -0.22 |

250 cells qualify out of 6705 with ≥30 trades. With this many cells, a few will pass by luck alone; t here is a per-cell screen, not corrected for the number of cells tried.

## 3 · Every setup, overall (default variant, all timeframes but 1m; std = 1R first target, trend = 2R first target, 15m+ only)

| setup | sym | exit | trades | win | avg R | first half | second half |
|---|---|---|---|---|---|---|---|
| dtfx_close_fib | AUDUSD | std | 274 | 33% | -0.314 | -0.35 | -0.28 |
| dtfx_close_fib | AUDUSD | trend | 74 | 20% | -0.458 | -0.53 | -0.39 |
| dtfx_close_fib | EURUSD | std | 264 | 42% | -0.149 | -0.19 | -0.11 |
| dtfx_close_fib | EURUSD | trend | 59 | 47% | +0.015 | +0.17 | -0.12 |
| dtfx_close_fib | GBPUSD | std | 237 | 40% | -0.233 | -0.19 | -0.28 |
| dtfx_close_fib | GBPUSD | trend | 56 | 29% | -0.166 | -0.31 | -0.06 |
| dtfx_close_fib | NDQ | std | 279 | 52% | -0.027 | +0.00 | -0.07 |
| dtfx_close_fib | NDQ | trend | 60 | 45% | -0.023 | -0.14 | +0.14 |
| dtfx_close_fib | US30 | std | 280 | 45% | -0.086 | -0.04 | -0.13 |
| dtfx_close_fib | US30 | trend | 57 | 44% | +0.084 | +0.11 | +0.06 |
| dtfx_close_fib | XAUUSD | std | 316 | 51% | +0.011 | +0.00 | +0.02 |
| dtfx_close_fib | XAUUSD | trend | 73 | 45% | -0.061 | +0.06 | -0.18 |
| dtfx_close_fib_brk | AUDUSD | std | 236 | 29% | -0.377 | -0.45 | -0.31 |
| dtfx_close_fib_brk | AUDUSD | trend | 64 | 20% | -0.500 | -0.61 | -0.39 |
| dtfx_close_fib_brk | EURUSD | std | 213 | 41% | -0.192 | -0.14 | -0.24 |
| dtfx_close_fib_brk | EURUSD | trend | 45 | 42% | +0.042 | +0.26 | -0.23 |
| dtfx_close_fib_brk | GBPUSD | std | 207 | 38% | -0.282 | -0.26 | -0.31 |
| dtfx_close_fib_brk | GBPUSD | trend | 50 | 34% | -0.119 | -0.01 | -0.23 |
| dtfx_close_fib_brk | NDQ | std | 217 | 51% | -0.041 | +0.00 | -0.09 |
| dtfx_close_fib_brk | NDQ | trend | 37 | 46% | +0.121 | -0.00 | +0.42 |
| dtfx_close_fib_brk | US30 | std | 214 | 45% | -0.076 | +0.06 | -0.20 |
| dtfx_close_fib_brk | US30 | trend | 47 | 43% | +0.116 | +0.29 | -0.07 |
| dtfx_close_fib_brk | XAUUSD | std | 246 | 51% | -0.015 | -0.05 | +0.02 |
| dtfx_close_fib_brk | XAUUSD | trend | 55 | 44% | -0.155 | -0.19 | -0.12 |
| dtfx_close_origin | AUDUSD | std | 246 | 33% | -0.335 | -0.40 | -0.27 |
| dtfx_close_origin | AUDUSD | trend | 60 | 35% | -0.235 | -0.46 | -0.04 |
| dtfx_close_origin | EURUSD | std | 230 | 41% | -0.164 | -0.21 | -0.13 |
| dtfx_close_origin | EURUSD | trend | 63 | 30% | -0.242 | -0.44 | -0.08 |
| dtfx_close_origin | GBPUSD | std | 217 | 40% | -0.229 | -0.15 | -0.32 |
| dtfx_close_origin | GBPUSD | trend | 56 | 34% | -0.057 | -0.22 | +0.07 |
| dtfx_close_origin | NDQ | std | 261 | 48% | -0.050 | -0.11 | +0.02 |
| dtfx_close_origin | NDQ | trend | 56 | 39% | -0.059 | -0.23 | +0.07 |
| dtfx_close_origin | US30 | std | 324 | 46% | -0.077 | +0.02 | -0.16 |
| dtfx_close_origin | US30 | trend | 77 | 43% | +0.034 | +0.12 | -0.05 |
| dtfx_close_origin | XAUUSD | std | 303 | 46% | -0.092 | -0.06 | -0.14 |
| dtfx_close_origin | XAUUSD | trend | 60 | 32% | -0.347 | -0.17 | -0.56 |
| dtfx_wick_fib | AUDUSD | std | 389 | 35% | -0.262 | -0.29 | -0.23 |
| dtfx_wick_fib | AUDUSD | trend | 94 | 29% | -0.265 | -0.38 | -0.17 |
| dtfx_wick_fib | EURUSD | std | 379 | 44% | -0.150 | -0.14 | -0.16 |
| dtfx_wick_fib | EURUSD | trend | 83 | 48% | +0.109 | +0.10 | +0.11 |
| dtfx_wick_fib | GBPUSD | std | 378 | 42% | -0.202 | -0.13 | -0.28 |
| dtfx_wick_fib | GBPUSD | trend | 93 | 28% | -0.229 | -0.18 | -0.27 |
| dtfx_wick_fib | NDQ | std | 427 | 51% | -0.042 | -0.03 | -0.05 |
| dtfx_wick_fib | NDQ | trend | 97 | 44% | -0.049 | -0.21 | +0.13 |
| dtfx_wick_fib | US30 | std | 417 | 48% | -0.032 | -0.03 | -0.04 |
| dtfx_wick_fib | US30 | trend | 72 | 36% | -0.132 | -0.06 | -0.19 |
| dtfx_wick_fib | XAUUSD | std | 457 | 53% | +0.042 | +0.08 | -0.00 |
| dtfx_wick_fib | XAUUSD | trend | 118 | 51% | +0.082 | +0.25 | -0.09 |
| dtfx_zone | AUDUSD | std | 1101 | 36% | -0.247 | -0.26 | -0.23 |
| dtfx_zone | AUDUSD | trend | 272 | 32% | -0.252 | -0.24 | -0.26 |
| dtfx_zone | EURUSD | std | 1072 | 40% | -0.194 | -0.23 | -0.16 |
| dtfx_zone | EURUSD | trend | 246 | 30% | -0.300 | -0.39 | -0.19 |
| dtfx_zone | GBPUSD | std | 1141 | 38% | -0.226 | -0.23 | -0.22 |
| dtfx_zone | GBPUSD | trend | 246 | 35% | -0.104 | -0.10 | -0.11 |
| dtfx_zone | NDQ | std | 1077 | 47% | -0.078 | -0.13 | -0.03 |
| dtfx_zone | NDQ | trend | 217 | 43% | -0.039 | -0.07 | -0.01 |
| dtfx_zone | US30 | std | 1112 | 44% | -0.121 | -0.14 | -0.10 |
| dtfx_zone | US30 | trend | 223 | 37% | -0.053 | -0.12 | +0.00 |
| dtfx_zone | XAUUSD | std | 1114 | 50% | -0.038 | +0.02 | -0.11 |
| dtfx_zone | XAUUSD | trend | 254 | 50% | +0.040 | +0.02 | +0.06 |
| ict_2022 | AUDUSD | std | 112 | 45% | -0.141 | -0.25 | -0.02 |
| ict_2022 | AUDUSD | trend | 23 | 26% | -0.276 | -0.27 | -0.29 |
| ict_2022 | EURUSD | std | 136 | 43% | -0.124 | -0.15 | -0.10 |
| ict_2022 | EURUSD | trend | 39 | 33% | -0.152 | -0.26 | +0.01 |
| ict_2022 | GBPUSD | std | 158 | 41% | -0.245 | -0.26 | -0.23 |
| ict_2022 | GBPUSD | trend | 45 | 31% | -0.193 | -0.32 | -0.05 |
| ict_2022 | NDQ | std | 141 | 37% | -0.229 | -0.34 | -0.09 |
| ict_2022 | NDQ | trend | 29 | 38% | -0.104 | -0.19 | -0.05 |
| ict_2022 | US30 | std | 149 | 40% | -0.197 | -0.11 | -0.28 |
| ict_2022 | US30 | trend | 33 | 42% | -0.053 | -0.21 | +0.08 |
| ict_2022 | XAUUSD | std | 101 | 46% | -0.128 | -0.09 | -0.17 |
| ict_2022 | XAUUSD | trend | 24 | 54% | +0.344 | +0.18 | +0.48 |
| ict_amd | AUDUSD | std | 183 | 42% | -0.173 | -0.12 | -0.24 |
| ict_amd | AUDUSD | trend | 77 | 40% | -0.024 | -0.16 | +0.18 |
| ict_amd | EURUSD | std | 271 | 49% | -0.026 | +0.06 | -0.14 |
| ict_amd | EURUSD | trend | 137 | 43% | -0.030 | -0.07 | +0.02 |
| ict_amd | GBPUSD | std | 289 | 45% | -0.010 | -0.01 | -0.02 |
| ict_amd | GBPUSD | trend | 136 | 44% | +0.065 | -0.03 | +0.21 |
| ict_amd | NDQ | std | 256 | 47% | -0.005 | -0.08 | +0.10 |
| ict_amd | NDQ | trend | 124 | 45% | +0.047 | -0.07 | +0.20 |
| ict_amd | US30 | std | 353 | 44% | -0.049 | -0.10 | +0.00 |
| ict_amd | US30 | trend | 177 | 29% | -0.197 | -0.12 | -0.28 |
| ict_amd | XAUUSD | std | 175 | 49% | -0.034 | +0.02 | -0.13 |
| ict_amd | XAUUSD | trend | 76 | 61% | +0.061 | +0.08 | +0.02 |
| ict_fvg_sweep | AUDUSD | std | 219 | 38% | -0.256 | -0.25 | -0.26 |
| ict_fvg_sweep | AUDUSD | trend | 59 | 37% | -0.032 | +0.13 | -0.17 |
| ict_fvg_sweep | EURUSD | std | 194 | 44% | -0.069 | -0.15 | +0.03 |
| ict_fvg_sweep | EURUSD | trend | 54 | 30% | -0.312 | -0.33 | -0.29 |
| ict_fvg_sweep | GBPUSD | std | 211 | 41% | -0.236 | -0.28 | -0.20 |
| ict_fvg_sweep | GBPUSD | trend | 59 | 39% | -0.180 | -0.23 | -0.13 |
| ict_fvg_sweep | NDQ | std | 200 | 42% | -0.157 | -0.36 | +0.01 |
| ict_fvg_sweep | NDQ | trend | 39 | 23% | -0.493 | -0.91 | -0.28 |
| ict_fvg_sweep | US30 | std | 225 | 48% | +0.017 | -0.06 | +0.10 |
| ict_fvg_sweep | US30 | trend | 45 | 40% | +0.041 | -0.34 | +0.52 |
| ict_fvg_sweep | XAUUSD | std | 185 | 51% | +0.013 | +0.05 | -0.03 |
| ict_fvg_sweep | XAUUSD | trend | 38 | 47% | +0.342 | +0.33 | +0.36 |
| ict_ote | AUDUSD | std | 746 | 37% | -0.285 | -0.29 | -0.28 |
| ict_ote | AUDUSD | trend | 235 | 34% | -0.230 | -0.17 | -0.28 |
| ict_ote | EURUSD | std | 722 | 39% | -0.251 | -0.26 | -0.24 |
| ict_ote | EURUSD | trend | 223 | 25% | -0.327 | -0.40 | -0.27 |
| ict_ote | GBPUSD | std | 773 | 40% | -0.197 | -0.19 | -0.21 |
| ict_ote | GBPUSD | trend | 246 | 34% | -0.114 | -0.03 | -0.19 |
| ict_ote | NDQ | std | 768 | 48% | -0.050 | -0.11 | +0.00 |
| ict_ote | NDQ | trend | 200 | 42% | +0.027 | -0.03 | +0.06 |
| ict_ote | US30 | std | 793 | 43% | -0.105 | -0.09 | -0.11 |
| ict_ote | US30 | trend | 210 | 38% | +0.060 | -0.12 | +0.19 |
| ict_ote | XAUUSD | std | 768 | 49% | -0.041 | -0.04 | -0.04 |
| ict_ote | XAUUSD | trend | 199 | 42% | -0.064 | -0.06 | -0.07 |
| ict_silver_bullet | AUDUSD | std | 335 | 36% | -0.332 | -0.29 | -0.37 |
| ict_silver_bullet | AUDUSD | trend | 10 | 30% | -0.163 | +0.28 | -0.82 |
| ict_silver_bullet | EURUSD | std | 364 | 41% | -0.229 | -0.20 | -0.25 |
| ict_silver_bullet | EURUSD | trend | 9 | 56% | +0.576 | +0.29 | +0.80 |
| ict_silver_bullet | GBPUSD | std | 350 | 39% | -0.279 | -0.18 | -0.38 |
| ict_silver_bullet | GBPUSD | trend | 9 | 33% | -0.140 | +0.34 | -0.73 |
| ict_silver_bullet | NDQ | std | 318 | 44% | -0.103 | -0.19 | -0.04 |
| ict_silver_bullet | NDQ | trend | 19 | 47% | +0.138 | +0.45 | -0.29 |
| ict_silver_bullet | US30 | std | 371 | 47% | -0.034 | -0.01 | -0.06 |
| ict_silver_bullet | US30 | trend | 17 | 47% | +0.071 | +0.24 | -0.34 |
| ict_silver_bullet | XAUUSD | std | 326 | 45% | -0.072 | -0.12 | -0.01 |
| ict_silver_bullet | XAUUSD | trend | 2 | 50% | +0.321 | +0.32 | — |
| ict_turtle_soup | AUDUSD | std | 1129 | 36% | -0.336 | -0.28 | -0.42 |
| ict_turtle_soup | AUDUSD | trend | 317 | 31% | -0.238 | -0.16 | -0.32 |
| ict_turtle_soup | EURUSD | std | 1125 | 38% | -0.267 | -0.27 | -0.27 |
| ict_turtle_soup | EURUSD | trend | 349 | 33% | -0.144 | -0.18 | -0.11 |
| ict_turtle_soup | GBPUSD | std | 1248 | 36% | -0.265 | -0.23 | -0.33 |
| ict_turtle_soup | GBPUSD | trend | 389 | 31% | -0.145 | -0.08 | -0.23 |
| ict_turtle_soup | NDQ | std | 2058 | 46% | -0.087 | -0.10 | -0.07 |
| ict_turtle_soup | NDQ | trend | 386 | 36% | -0.015 | -0.03 | -0.00 |
| ict_turtle_soup | US30 | std | 2258 | 45% | -0.105 | -0.13 | -0.08 |
| ict_turtle_soup | US30 | trend | 419 | 34% | -0.097 | -0.14 | -0.06 |
| ict_turtle_soup | XAUUSD | std | 1973 | 46% | -0.081 | -0.08 | -0.08 |
| ict_turtle_soup | XAUUSD | trend | 345 | 38% | -0.086 | -0.03 | -0.14 |
| london_breakout | AUDUSD | std | 218 | 40% | -0.241 | -0.41 | -0.11 |
| london_breakout | AUDUSD | trend | 98 | 49% | +0.120 | -0.28 | +0.40 |
| london_breakout | EURUSD | std | 311 | 48% | -0.041 | -0.07 | -0.02 |
| london_breakout | EURUSD | trend | 153 | 49% | +0.083 | -0.17 | +0.30 |
| london_breakout | GBPUSD | std | 329 | 46% | -0.063 | -0.07 | -0.05 |
| london_breakout | GBPUSD | trend | 167 | 38% | -0.035 | -0.22 | +0.22 |
| london_breakout | NDQ | std | 237 | 46% | -0.087 | -0.17 | +0.00 |
| london_breakout | NDQ | trend | 105 | 41% | +0.030 | -0.23 | +0.32 |
| london_breakout | US30 | std | 296 | 45% | -0.097 | -0.28 | +0.06 |
| london_breakout | US30 | trend | 139 | 29% | -0.167 | -0.25 | -0.10 |
| london_breakout | XAUUSD | std | 177 | 49% | -0.015 | -0.12 | +0.07 |
| london_breakout | XAUUSD | trend | 81 | 51% | +0.236 | -0.07 | +0.44 |
| macd_cross | AUDUSD | std | 610 | 41% | -0.226 | -0.25 | -0.21 |
| macd_cross | AUDUSD | trend | 107 | 46% | +0.003 | -0.03 | +0.03 |
| macd_cross | EURUSD | std | 598 | 46% | -0.114 | -0.10 | -0.13 |
| macd_cross | EURUSD | trend | 126 | 41% | +0.010 | -0.00 | +0.02 |
| macd_cross | GBPUSD | std | 616 | 41% | -0.182 | -0.15 | -0.22 |
| macd_cross | GBPUSD | trend | 125 | 35% | -0.073 | -0.12 | -0.02 |
| macd_cross | NDQ | std | 567 | 48% | -0.006 | -0.03 | +0.01 |
| macd_cross | NDQ | trend | 106 | 52% | +0.130 | +0.11 | +0.15 |
| macd_cross | US30 | std | 592 | 49% | -0.042 | -0.08 | -0.01 |
| macd_cross | US30 | trend | 104 | 42% | -0.088 | -0.27 | +0.12 |
| macd_cross | XAUUSD | std | 613 | 47% | -0.062 | -0.03 | -0.11 |
| macd_cross | XAUUSD | trend | 126 | 33% | -0.178 | -0.09 | -0.27 |
| rsi_pullback | AUDUSD | std | 528 | 32% | -0.423 | -0.37 | -0.47 |
| rsi_pullback | AUDUSD | trend | 112 | 41% | -0.070 | +0.19 | -0.21 |
| rsi_pullback | EURUSD | std | 569 | 38% | -0.268 | -0.28 | -0.26 |
| rsi_pullback | EURUSD | trend | 131 | 37% | -0.092 | +0.08 | -0.25 |
| rsi_pullback | GBPUSD | std | 516 | 31% | -0.398 | -0.50 | -0.30 |
| rsi_pullback | GBPUSD | trend | 118 | 30% | -0.222 | -0.30 | -0.16 |
| rsi_pullback | NDQ | std | 545 | 45% | -0.126 | -0.13 | -0.13 |
| rsi_pullback | NDQ | trend | 142 | 40% | -0.052 | +0.10 | -0.15 |
| rsi_pullback | US30 | std | 572 | 45% | -0.124 | -0.21 | -0.04 |
| rsi_pullback | US30 | trend | 125 | 34% | -0.082 | -0.13 | -0.04 |
| rsi_pullback | XAUUSD | std | 476 | 53% | -0.005 | -0.05 | +0.05 |
| rsi_pullback | XAUUSD | trend | 124 | 51% | +0.271 | +0.31 | +0.23 |
| smc_bos_retest | AUDUSD | std | 920 | 36% | -0.276 | -0.33 | -0.23 |
| smc_bos_retest | AUDUSD | trend | 232 | 29% | -0.225 | -0.29 | -0.16 |
| smc_bos_retest | EURUSD | std | 848 | 40% | -0.166 | -0.18 | -0.15 |
| smc_bos_retest | EURUSD | trend | 193 | 45% | +0.021 | -0.04 | +0.07 |
| smc_bos_retest | GBPUSD | std | 863 | 39% | -0.202 | -0.16 | -0.25 |
| smc_bos_retest | GBPUSD | trend | 201 | 37% | -0.101 | -0.06 | -0.13 |
| smc_bos_retest | NDQ | std | 941 | 47% | -0.055 | -0.10 | -0.02 |
| smc_bos_retest | NDQ | trend | 217 | 45% | +0.019 | -0.19 | +0.19 |
| smc_bos_retest | US30 | std | 956 | 44% | -0.097 | -0.10 | -0.09 |
| smc_bos_retest | US30 | trend | 211 | 36% | -0.149 | -0.16 | -0.14 |
| smc_bos_retest | XAUUSD | std | 1021 | 50% | +0.018 | +0.04 | -0.00 |
| smc_bos_retest | XAUUSD | trend | 241 | 50% | +0.084 | +0.11 | +0.06 |
| smc_breaker | AUDUSD | std | 382 | 34% | -0.336 | -0.30 | -0.38 |
| smc_breaker | AUDUSD | trend | 99 | 25% | -0.351 | -0.48 | -0.17 |
| smc_breaker | EURUSD | std | 414 | 36% | -0.316 | -0.19 | -0.45 |
| smc_breaker | EURUSD | trend | 89 | 33% | -0.092 | +0.17 | -0.37 |
| smc_breaker | GBPUSD | std | 429 | 30% | -0.438 | -0.37 | -0.51 |
| smc_breaker | GBPUSD | trend | 103 | 27% | -0.266 | -0.20 | -0.33 |
| smc_breaker | NDQ | std | 453 | 42% | -0.195 | -0.23 | -0.15 |
| smc_breaker | NDQ | trend | 83 | 40% | +0.035 | +0.11 | -0.05 |
| smc_breaker | US30 | std | 443 | 43% | -0.126 | -0.17 | -0.08 |
| smc_breaker | US30 | trend | 93 | 38% | -0.072 | -0.25 | +0.10 |
| smc_breaker | XAUUSD | std | 396 | 46% | -0.046 | -0.08 | -0.02 |
| smc_breaker | XAUUSD | trend | 91 | 40% | -0.005 | -0.27 | +0.17 |
| smc_choch | AUDUSD | std | 965 | 40% | -0.191 | -0.17 | -0.22 |
| smc_choch | AUDUSD | trend | 224 | 34% | -0.157 | -0.25 | -0.08 |
| smc_choch | EURUSD | std | 996 | 43% | -0.131 | -0.14 | -0.12 |
| smc_choch | EURUSD | trend | 212 | 43% | -0.075 | -0.20 | +0.03 |
| smc_choch | GBPUSD | std | 1046 | 39% | -0.226 | -0.21 | -0.24 |
| smc_choch | GBPUSD | trend | 244 | 35% | -0.078 | -0.11 | -0.05 |
| smc_choch | NDQ | std | 1011 | 47% | -0.046 | -0.09 | -0.01 |
| smc_choch | NDQ | trend | 177 | 46% | +0.037 | -0.14 | +0.17 |
| smc_choch | US30 | std | 1038 | 47% | -0.066 | -0.04 | -0.09 |
| smc_choch | US30 | trend | 200 | 36% | -0.056 | -0.09 | -0.03 |
| smc_choch | XAUUSD | std | 1071 | 50% | -0.013 | -0.01 | -0.01 |
| smc_choch | XAUUSD | trend | 204 | 42% | -0.057 | -0.05 | -0.07 |
| smc_displacement | AUDUSD | std | 460 | 31% | -0.402 | -0.36 | -0.44 |
| smc_displacement | AUDUSD | trend | 103 | 24% | -0.399 | -0.47 | -0.32 |
| smc_displacement | EURUSD | std | 466 | 35% | -0.339 | -0.41 | -0.29 |
| smc_displacement | EURUSD | trend | 100 | 26% | -0.297 | -0.44 | -0.16 |
| smc_displacement | GBPUSD | std | 501 | 36% | -0.272 | -0.22 | -0.33 |
| smc_displacement | GBPUSD | trend | 95 | 33% | -0.053 | -0.04 | -0.06 |
| smc_displacement | NDQ | std | 415 | 48% | -0.021 | -0.06 | +0.02 |
| smc_displacement | NDQ | trend | 65 | 38% | -0.018 | -0.27 | +0.24 |
| smc_displacement | US30 | std | 409 | 45% | -0.102 | -0.17 | -0.04 |
| smc_displacement | US30 | trend | 66 | 33% | -0.243 | -0.30 | -0.19 |
| smc_displacement | XAUUSD | std | 425 | 49% | -0.003 | -0.03 | +0.02 |
| smc_displacement | XAUUSD | trend | 72 | 49% | +0.166 | +0.40 | -0.07 |
| smc_ifvg | AUDUSD | std | 1860 | 31% | -0.436 | -0.39 | -0.48 |
| smc_ifvg | AUDUSD | trend | 285 | 25% | -0.376 | -0.28 | -0.46 |
| smc_ifvg | EURUSD | std | 1848 | 33% | -0.378 | -0.37 | -0.38 |
| smc_ifvg | EURUSD | trend | 313 | 35% | -0.064 | -0.14 | +0.01 |
| smc_ifvg | GBPUSD | std | 1794 | 31% | -0.434 | -0.38 | -0.49 |
| smc_ifvg | GBPUSD | trend | 252 | 28% | -0.260 | -0.26 | -0.26 |
| smc_ifvg | NDQ | std | 1453 | 47% | -0.044 | -0.12 | +0.02 |
| smc_ifvg | NDQ | trend | 230 | 35% | -0.056 | -0.12 | -0.00 |
| smc_ifvg | US30 | std | 1676 | 43% | -0.144 | -0.14 | -0.15 |
| smc_ifvg | US30 | trend | 227 | 33% | -0.089 | -0.12 | -0.05 |
| smc_ifvg | XAUUSD | std | 1513 | 48% | -0.045 | -0.08 | -0.01 |
| smc_ifvg | XAUUSD | trend | 258 | 40% | +0.044 | +0.05 | +0.04 |
| smc_liquidity_sweep | AUDUSD | std | 151 | 44% | -0.130 | -0.11 | -0.14 |
| smc_liquidity_sweep | AUDUSD | trend | 102 | 35% | -0.146 | -0.24 | -0.06 |
| smc_liquidity_sweep | EURUSD | std | 183 | 43% | -0.162 | -0.03 | -0.33 |
| smc_liquidity_sweep | EURUSD | trend | 124 | 40% | -0.041 | -0.04 | -0.04 |
| smc_liquidity_sweep | GBPUSD | std | 203 | 45% | -0.101 | -0.02 | -0.22 |
| smc_liquidity_sweep | GBPUSD | trend | 137 | 40% | -0.008 | +0.03 | -0.08 |
| smc_liquidity_sweep | NDQ | std | 175 | 47% | -0.030 | +0.08 | -0.16 |
| smc_liquidity_sweep | NDQ | trend | 109 | 47% | +0.068 | +0.09 | +0.05 |
| smc_liquidity_sweep | US30 | std | 212 | 45% | -0.040 | +0.05 | -0.11 |
| smc_liquidity_sweep | US30 | trend | 139 | 34% | -0.027 | +0.10 | -0.15 |
| smc_liquidity_sweep | XAUUSD | std | 114 | 49% | -0.080 | -0.10 | -0.05 |
| smc_liquidity_sweep | XAUUSD | trend | 73 | 47% | -0.029 | -0.12 | +0.07 |
| smc_mss | AUDUSD | std | 352 | 40% | -0.217 | -0.25 | -0.19 |
| smc_mss | AUDUSD | trend | 74 | 41% | +0.002 | -0.12 | +0.09 |
| smc_mss | EURUSD | std | 394 | 45% | -0.108 | -0.19 | -0.04 |
| smc_mss | EURUSD | trend | 85 | 46% | -0.051 | -0.29 | +0.22 |
| smc_mss | GBPUSD | std | 476 | 41% | -0.143 | -0.11 | -0.18 |
| smc_mss | GBPUSD | trend | 114 | 37% | -0.034 | -0.14 | +0.09 |
| smc_mss | NDQ | std | 396 | 44% | -0.070 | -0.08 | -0.06 |
| smc_mss | NDQ | trend | 81 | 40% | -0.037 | +0.13 | -0.15 |
| smc_mss | US30 | std | 419 | 47% | -0.034 | -0.07 | -0.00 |
| smc_mss | US30 | trend | 87 | 39% | +0.002 | -0.31 | +0.28 |
| smc_mss | XAUUSD | std | 320 | 46% | -0.084 | -0.11 | -0.05 |
| smc_mss | XAUUSD | trend | 67 | 49% | -0.052 | +0.00 | -0.11 |
| smc_order_block | AUDUSD | std | 1063 | 29% | -0.458 | -0.41 | -0.50 |
| smc_order_block | AUDUSD | trend | 210 | 21% | -0.431 | -0.46 | -0.40 |
| smc_order_block | EURUSD | std | 1027 | 30% | -0.429 | -0.44 | -0.42 |
| smc_order_block | EURUSD | trend | 221 | 32% | -0.147 | -0.40 | +0.12 |
| smc_order_block | GBPUSD | std | 1053 | 30% | -0.464 | -0.45 | -0.48 |
| smc_order_block | GBPUSD | trend | 223 | 27% | -0.308 | -0.33 | -0.29 |
| smc_order_block | NDQ | std | 1001 | 44% | -0.129 | -0.17 | -0.10 |
| smc_order_block | NDQ | trend | 200 | 36% | -0.059 | -0.22 | +0.06 |
| smc_order_block | US30 | std | 980 | 42% | -0.149 | -0.14 | -0.16 |
| smc_order_block | US30 | trend | 185 | 36% | -0.024 | -0.15 | +0.09 |
| smc_order_block | XAUUSD | std | 1037 | 47% | -0.062 | -0.06 | -0.06 |
| smc_order_block | XAUUSD | trend | 209 | 32% | -0.172 | -0.22 | -0.13 |
| smt_divergence | NDQ | std | 342 | 46% | -0.056 | -0.07 | -0.04 |
| smt_divergence | NDQ | trend | 80 | 40% | +0.043 | -0.05 | +0.12 |
| smt_divergence | US30 | std | 384 | 42% | -0.123 | -0.07 | -0.18 |
| smt_divergence | US30 | trend | 103 | 28% | -0.272 | -0.33 | -0.22 |
| sr_rejection | AUDUSD | std | 2446 | 29% | -0.484 | -0.45 | -0.51 |
| sr_rejection | AUDUSD | trend | 499 | 27% | -0.304 | -0.29 | -0.32 |
| sr_rejection | EURUSD | std | 2270 | 32% | -0.410 | -0.43 | -0.39 |
| sr_rejection | EURUSD | trend | 493 | 31% | -0.181 | -0.12 | -0.23 |
| sr_rejection | GBPUSD | std | 2501 | 30% | -0.436 | -0.41 | -0.47 |
| sr_rejection | GBPUSD | trend | 510 | 27% | -0.285 | -0.30 | -0.27 |
| sr_rejection | NDQ | std | 2482 | 45% | -0.089 | -0.08 | -0.10 |
| sr_rejection | NDQ | trend | 425 | 35% | -0.057 | -0.08 | -0.03 |
| sr_rejection | US30 | std | 2247 | 44% | -0.111 | -0.13 | -0.09 |
| sr_rejection | US30 | trend | 426 | 37% | +0.035 | -0.02 | +0.09 |
| sr_rejection | XAUUSD | std | 2835 | 45% | -0.126 | -0.11 | -0.14 |
| sr_rejection | XAUUSD | trend | 543 | 35% | -0.081 | +0.04 | -0.21 |
| stoic_sbs | AUDUSD | std | 63 | 29% | -0.445 | -0.50 | -0.39 |
| stoic_sbs | AUDUSD | trend | 21 | 43% | +0.087 | +0.00 | +0.20 |
| stoic_sbs | EURUSD | std | 74 | 49% | -0.105 | -0.00 | -0.20 |
| stoic_sbs | EURUSD | trend | 19 | 32% | -0.270 | -0.38 | -0.21 |
| stoic_sbs | GBPUSD | std | 92 | 41% | -0.263 | -0.36 | -0.14 |
| stoic_sbs | GBPUSD | trend | 24 | 29% | -0.249 | -0.34 | -0.16 |
| stoic_sbs | NDQ | std | 86 | 45% | -0.162 | +0.02 | -0.37 |
| stoic_sbs | NDQ | trend | 10 | 20% | -0.770 | -1.00 | -0.42 |
| stoic_sbs | US30 | std | 77 | 53% | -0.036 | -0.05 | -0.02 |
| stoic_sbs | US30 | trend | 14 | 21% | -0.585 | -1.00 | -0.03 |
| stoic_sbs | XAUUSD | std | 89 | 52% | +0.028 | +0.06 | -0.00 |
| stoic_sbs | XAUUSD | trend | 15 | 47% | -0.281 | -0.45 | -0.13 |
| trend_breakout | AUDUSD | std | 315 | 37% | -0.257 | -0.33 | -0.19 |
| trend_breakout | AUDUSD | trend | 306 | 29% | -0.232 | -0.38 | -0.11 |
| trend_breakout | EURUSD | std | 254 | 38% | -0.170 | -0.18 | -0.16 |
| trend_breakout | EURUSD | trend | 250 | 31% | -0.124 | -0.17 | -0.08 |
| trend_breakout | GBPUSD | std | 279 | 39% | -0.198 | -0.13 | -0.27 |
| trend_breakout | GBPUSD | trend | 273 | 28% | -0.204 | -0.11 | -0.30 |
| trend_breakout | NDQ | std | 275 | 52% | +0.019 | +0.06 | -0.01 |
| trend_breakout | NDQ | trend | 266 | 41% | +0.031 | +0.05 | +0.02 |
| trend_breakout | US30 | std | 230 | 50% | -0.028 | -0.03 | -0.02 |
| trend_breakout | US30 | trend | 225 | 37% | -0.002 | +0.05 | -0.05 |
| trend_breakout | XAUUSD | std | 258 | 54% | +0.093 | +0.18 | +0.01 |
| trend_breakout | XAUUSD | trend | 257 | 45% | +0.116 | +0.20 | +0.04 |
| trend_pullback | AUDUSD | std | 125 | 44% | -0.177 | -0.28 | -0.07 |
| trend_pullback | AUDUSD | trend | 121 | 30% | -0.281 | -0.35 | -0.21 |
| trend_pullback | EURUSD | std | 117 | 36% | -0.265 | -0.22 | -0.30 |
| trend_pullback | EURUSD | trend | 113 | 27% | -0.278 | -0.30 | -0.26 |
| trend_pullback | GBPUSD | std | 150 | 45% | -0.098 | -0.10 | -0.10 |
| trend_pullback | GBPUSD | trend | 145 | 33% | -0.176 | -0.17 | -0.18 |
| trend_pullback | NDQ | std | 125 | 58% | +0.076 | -0.15 | +0.22 |
| trend_pullback | NDQ | trend | 121 | 49% | +0.100 | -0.18 | +0.28 |
| trend_pullback | US30 | std | 118 | 43% | -0.123 | -0.23 | -0.02 |
| trend_pullback | US30 | trend | 114 | 34% | -0.122 | -0.28 | +0.03 |
| trend_pullback | XAUUSD | std | 105 | 50% | -0.002 | +0.19 | -0.28 |
| trend_pullback | XAUUSD | trend | 103 | 44% | -0.040 | +0.27 | -0.47 |
| vwap | AUDUSD | std | 1062 | 31% | -0.402 | -0.37 | -0.43 |
| vwap | AUDUSD | trend | 331 | 29% | -0.260 | -0.23 | -0.29 |
| vwap | EURUSD | std | 1090 | 37% | -0.312 | -0.29 | -0.33 |
| vwap | EURUSD | trend | 362 | 30% | -0.224 | -0.33 | -0.13 |
| vwap | GBPUSD | std | 1059 | 34% | -0.372 | -0.32 | -0.42 |
| vwap | GBPUSD | trend | 350 | 26% | -0.341 | -0.33 | -0.35 |
| vwap | NDQ | std | 900 | 43% | -0.133 | -0.33 | +0.01 |
| vwap | NDQ | trend | 273 | 40% | +0.018 | -0.22 | +0.18 |
| vwap | US30 | std | 1120 | 47% | -0.044 | -0.09 | -0.01 |
| vwap | US30 | trend | 361 | 33% | -0.098 | -0.23 | +0.01 |
| vwap | XAUUSD | std | 1088 | 49% | -0.016 | -0.04 | +0.01 |
| vwap | XAUUSD | trend | 308 | 40% | +0.058 | -0.04 | +0.20 |
| zone_confluence | AUDUSD | std | 632 | 37% | -0.306 | -0.28 | -0.33 |
| zone_confluence | AUDUSD | trend | 147 | 29% | -0.291 | -0.22 | -0.36 |
| zone_confluence | EURUSD | std | 643 | 39% | -0.255 | -0.27 | -0.24 |
| zone_confluence | EURUSD | trend | 169 | 33% | -0.197 | -0.28 | -0.11 |
| zone_confluence | GBPUSD | std | 683 | 36% | -0.307 | -0.29 | -0.32 |
| zone_confluence | GBPUSD | trend | 173 | 32% | -0.226 | -0.20 | -0.25 |
| zone_confluence | NDQ | std | 658 | 43% | -0.145 | -0.23 | -0.07 |
| zone_confluence | NDQ | trend | 142 | 35% | -0.160 | -0.16 | -0.16 |
| zone_confluence | US30 | std | 689 | 43% | -0.119 | -0.15 | -0.09 |
| zone_confluence | US30 | trend | 155 | 41% | +0.057 | -0.11 | +0.22 |
| zone_confluence | XAUUSD | std | 593 | 48% | -0.020 | +0.01 | -0.05 |
| zone_confluence | XAUUSD | trend | 136 | 40% | -0.111 | -0.12 | -0.10 |

## 3b · Exits compared (same signals, default variants, all instruments, 15m+ for trend)

std = 1R first target, half banked, runner trailed (the bot today) · scalp = all out at 1R, 30-min cap (≤5m) · trend = 2R first target + runner · tpX = all out at X R, no runner

| exit | trades | win | avg R | total R | per symbol (avg R) |
|---|---|---|---|---|---|
| scalp | 84097 | 39% | -0.208 | -17460 | AUDUSD -0.368 · EURUSD -0.321 · GBPUSD -0.349 · NDQ -0.084 · US30 -0.102 · XAUUSD -0.062 |
| std | 107106 | 41% | -0.186 | -19946 | AUDUSD -0.347 · EURUSD -0.264 · GBPUSD -0.303 · NDQ -0.078 · US30 -0.097 · XAUUSD -0.048 |
| trend | 26054 | 36% | -0.109 | -2828 | AUDUSD -0.246 · EURUSD -0.135 · GBPUSD -0.174 · NDQ -0.013 · US30 -0.062 · XAUUSD -0.007 |

## 4 · Best cell per setup (≥30 trades, by t-stat)

| setup | variant | sym | tf | exit | trades | win | avg R | t | quarters positive |
|---|---|---|---|---|---|---|---|---|---|
| dtfx_wick_fib | vol=impulse | XAUUSD | 3min | scalp | 64 | 72% | +0.255 | 2.7 | 4/4 |
| rsi_pullback | default | XAUUSD | 15min | std | 80 | 65% | +0.277 | 2.6 | 3/4 |
| ict_turtle_soup | level=session | US30 | 15min | trend | 62 | 50% | +0.557 | 2.5 | 4/4 |
| ict_amd | manip=ny | NDQ | 3min | scalp | 39 | 67% | +0.184 | 2.5 | 4/4 |
| smc_ifvg | default | XAUUSD | 15min | std | 147 | 60% | +0.182 | 2.3 | 4/4 |
| smc_choch | swing=2 | NDQ | 1h | trend | 38 | 63% | +0.285 | 2.2 | 4/4 |
| dtfx_zone | default | NDQ | 30min | std | 57 | 65% | +0.180 | 2.2 | 3/4 |
| trend_breakout | vol=impulse | US30 | 15min | trend | 32 | 56% | +0.679 | 2.2 | 4/4 |
| dtfx_close_fib | vol=impulse | XAUUSD | 3min | scalp | 45 | 71% | +0.237 | 2.2 | 3/4 |
| vwap | vol=dry | XAUUSD | 15min | std | 83 | 59% | +0.274 | 2.2 | 4/4 |
| smc_displacement | default | XAUUSD | 15min | trend | 41 | 51% | +0.451 | 2.1 | 3/4 |
| dtfx_close_fib_brk | vol=impulse | US30 | 1min | std | 101 | 61% | +0.213 | 2.0 | 3/4 |
| smc_bos_retest | tol_atr=0.15 | EURUSD | 1h | trend | 33 | 58% | +0.254 | 1.8 | 4/4 |
| dtfx_close_origin | swing=pb | XAUUSD | 3min | std | 125 | 58% | +0.153 | 1.7 | 3/4 |
| smt_divergence | confirm=reclaim | US30 | 1h | std | 41 | 63% | +0.270 | 1.6 | 4/4 |
| smc_mss | default | GBPUSD | 30min | std | 30 | 50% | +0.213 | 1.5 | 3/4 |
| london_breakout | default | EURUSD | 1h | trend | 36 | 67% | +0.181 | 1.5 | 3/4 |
| sr_rejection | default | NDQ | 30min | trend | 119 | 45% | +0.184 | 1.5 | 4/4 |
| trend_pullback | swing_bars=3 | XAUUSD | 30min | std | 33 | 64% | +0.237 | 1.5 | 3/4 |
| ict_ote | default | US30 | 30min | trend | 63 | 41% | +0.289 | 1.4 | 3/4 |
| ict_2022 | swing=3 | XAUUSD | 1min | std | 82 | 55% | +0.175 | 1.3 | 3/4 |
| macd_cross | default | NDQ | 5min | std | 178 | 53% | +0.098 | 1.3 | 3/4 |
| ict_silver_bullet | vol=dry | US30 | 3min | scalp | 113 | 55% | +0.095 | 1.2 | 4/4 |
| smc_order_block | default | US30 | 30min | trend | 57 | 44% | +0.173 | 0.9 | 3/4 |
| smc_liquidity_sweep | default | NDQ | 30min | trend | 32 | 50% | +0.191 | 0.9 | 3/4 |
| zone_confluence | within=4 | XAUUSD | 30min | std | 57 | 51% | +0.100 | 0.9 | 3/4 |
| stoic_sbs | default | XAUUSD | 3min | scalp | 44 | 57% | +0.108 | 0.8 | 3/4 |
| ict_fvg_sweep | default | XAUUSD | 5min | scalp | 53 | 57% | +0.060 | 0.8 | 2/4 |
| smc_breaker | default | US30 | 15min | trend | 55 | 40% | -0.005 | -0.0 | 2/4 |
