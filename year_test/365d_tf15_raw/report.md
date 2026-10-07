# Strategy test — 365 days · costs raw · 15min 30min 1h · tf15_raw

Created 2026-10-06 21:08 NY · trades 2025-10-06 → 2026-10-06 · 220,349 simulated trades · 5,376 cells

R is per trade in units of its own risk, after spread. Quarters split the period in four equal parts; an edge worth trading is positive in most quarters, not just on average. 1-minute cells are listed but the playbook doesn't trade 1m (spread is too large a share of the bar).

## 1 · The playbook system, replayed week by week on unseen data

Each week: pick cells from the trailing 60 days, trade them the next week, capacity rules on. This is the number that says whether the approach works.

- trades **761**, win rate **46%**, avg **-0.042R**, total **-32.06R**, profit factor 0.89, worst drawdown -41.26R, t-stat -1.31, chance it's really ≤0: 0.903
- without the 3 best trades: -47.87R
- XAUUSD: 440 trades, 48% win, -0.88R
- GBPUSD: 156 trades, 44% win, -23.27R
- EURUSD: 93 trades, 46% win, -3.14R
- AUDUSD: 18 trades, 17% win, -6.95R
- NDQ: 54 trades, 56% win, +2.18R

By month (R): 2025-11 -1.1 (5) · 2025-12 -20.9 (96) · 2026-01 -12.2 (38) · 2026-02 -7.0 (27) · 2026-03 +8.2 (58) · 2026-04 +11.0 (58) · 2026-05 -1.0 (76) · 2026-06 +4.0 (183) · 2026-07 -15.7 (99) · 2026-08 -15.6 (70) · 2026-09 +7.8 (38) · 2026-10 +2.0 (13)

Positive weeks: 18 of 46

## 2 · Cells that held up (≥30 trades, positive in both halves and ≥3 of 4 quarters)

| setup | variant | sym | tf | exit | trades | win | avg R | t | H1 | H2 | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| smc_displacement | disp_k=1.0 | XAUUSD | 15min | std | 68 | 68% | +0.295 | 2.6 | +0.38 | +0.16 | +0.30 | +0.50 | +0.07 | +0.27 |
| vwap | vol=dry | XAUUSD | 15min | trend | 83 | 48% | +0.406 | 2.6 | +0.36 | +0.45 | +0.31 | +0.41 | +0.52 | +0.38 |
| vwap | vol=dry | NDQ | 30min | std | 30 | 77% | +0.386 | 2.5 | +0.29 | +0.47 | +0.28 | +0.31 | +0.45 | +0.50 |
| vwap | vol=dry | XAUUSD | 15min | std | 85 | 60% | +0.329 | 2.5 | +0.33 | +0.33 | +0.23 | +0.42 | +0.53 | +0.16 |
| rsi_pullback | default | XAUUSD | 15min | std | 79 | 63% | +0.264 | 2.4 | +0.26 | +0.27 | +0.35 | +0.12 | -0.20 | +0.79 |
| trend_breakout | vol=impulse | US30 | 15min | trend | 33 | 58% | +0.651 | 2.4 | +0.94 | +0.37 | +1.01 | +0.88 | +0.66 | +0.18 |
| smc_displacement | swing=3 | XAUUSD | 15min | std | 45 | 69% | +0.340 | 2.4 | +0.43 | +0.18 | +0.33 | +0.64 | +0.24 | +0.14 |
| smc_displacement | default | XAUUSD | 15min | std | 50 | 68% | +0.316 | 2.4 | +0.48 | +0.07 | +0.31 | +0.86 | +0.05 | +0.10 |
| smc_displacement | entry=top | XAUUSD | 15min | trend | 65 | 51% | +0.392 | 2.4 | +0.70 | +0.01 | +0.61 | +0.86 | -0.02 | +0.02 |
| trend_breakout | vol=impulse | US30 | 15min | std | 34 | 71% | +0.417 | 2.3 | +0.48 | +0.35 | +0.66 | +0.32 | +0.44 | +0.29 |
| ict_turtle_soup | level=session | US30 | 15min | trend | 62 | 48% | +0.443 | 2.3 | +0.48 | +0.40 | +0.41 | +0.55 | +0.69 | +0.05 |
| smc_displacement | default | XAUUSD | 15min | trend | 50 | 52% | +0.437 | 2.3 | +0.70 | +0.04 | +0.74 | +0.61 | -0.10 | +0.14 |
| smc_ifvg | default | XAUUSD | 15min | std | 154 | 60% | +0.175 | 2.2 | +0.09 | +0.26 | -0.03 | +0.21 | +0.30 | +0.22 |
| ict_turtle_soup | level=session | US30 | 15min | std | 62 | 58% | +0.368 | 2.1 | +0.47 | +0.22 | +0.42 | +0.53 | +0.62 | -0.24 |
| sr_rejection | default | NDQ | 30min | trend | 117 | 48% | +0.269 | 2.1 | +0.19 | +0.36 | +0.28 | +0.10 | +0.20 | +0.49 |
| dtfx_zone | default | NDQ | 30min | std | 55 | 64% | +0.175 | 2.1 | +0.17 | +0.18 | +0.09 | +0.29 | +0.36 | -0.01 |
| smc_displacement | stop=fvg_bot | XAUUSD | 15min | trend | 50 | 50% | +0.424 | 2.1 | +0.57 | +0.21 | +0.44 | +0.86 | +0.17 | +0.24 |
| smc_displacement | disp_k=1.5 | XAUUSD | 15min | std | 30 | 70% | +0.340 | 2.1 | +0.47 | +0.19 | +0.24 | +1.17 | +0.24 | +0.15 |
| smc_displacement | swing=3 | XAUUSD | 15min | trend | 45 | 51% | +0.405 | 2.0 | +0.54 | +0.17 | +0.67 | +0.25 | -0.13 | +0.34 |
| rsi_pullback | default | XAUUSD | 15min | trend | 77 | 48% | +0.304 | 2.0 | +0.40 | +0.20 | +0.43 | +0.35 | -0.32 | +0.76 |
| vwap | tol_atr=0.3 | XAUUSD | 15min | trend | 211 | 42% | +0.190 | 2.0 | +0.11 | +0.28 | +0.15 | +0.07 | +0.36 | +0.19 |
| smc_choch | swing=2 | NDQ | 1h | trend | 38 | 61% | +0.240 | 2.0 | +0.25 | +0.23 | +0.27 | +0.22 | +0.28 | +0.18 |
| smc_bos_retest | stop=level | EURUSD | 1h | std | 37 | 54% | +0.206 | 2.0 | +0.21 | +0.20 | +0.30 | +0.17 | +0.33 | +0.13 |
| smc_bos_retest | tol_atr=0.3 | XAUUSD | 1h | trend | 45 | 62% | +0.195 | 2.0 | +0.34 | +0.03 | +0.30 | +0.40 | +0.05 | +0.01 |
| ict_turtle_soup | default | EURUSD | 1h | std | 40 | 62% | +0.208 | 1.9 | +0.21 | +0.21 | +0.42 | -0.02 | +0.26 | +0.16 |
| smc_displacement | disp_k=1.0 | XAUUSD | 15min | trend | 68 | 50% | +0.304 | 1.9 | +0.48 | +0.03 | +0.70 | +0.12 | -0.10 | +0.17 |
| smc_displacement | stop=fvg_bot | XAUUSD | 15min | std | 50 | 62% | +0.284 | 1.9 | +0.37 | +0.16 | +0.27 | +0.60 | +0.12 | +0.19 |
| dtfx_zone | default | NDQ | 1h | std | 33 | 58% | +0.151 | 1.9 | +0.21 | +0.08 | +0.11 | +0.35 | +0.18 | -0.04 |
| smc_bos_retest | swing=2 | XAUUSD | 1h | trend | 44 | 61% | +0.213 | 1.9 | +0.26 | +0.15 | +0.21 | +0.35 | +0.38 | -0.12 |
| dtfx_wick_fib | level=0.3 | GBPUSD | 30min | std | 52 | 63% | +0.180 | 1.8 | +0.34 | +0.03 | +0.39 | +0.28 | +0.06 | +0.00 |
| smc_choch | swing=2 | NDQ | 1h | std | 38 | 61% | +0.151 | 1.8 | +0.22 | +0.05 | +0.15 | +0.30 | +0.04 | +0.06 |
| ict_turtle_soup | confirm=choch | NDQ | 15min | trend | 64 | 55% | +0.262 | 1.8 | +0.12 | +0.36 | -0.02 | +0.24 | +0.35 | +0.39 |
| vwap | tol_atr=0.05 | XAUUSD | 15min | trend | 159 | 42% | +0.198 | 1.8 | +0.16 | +0.24 | +0.11 | +0.21 | +0.41 | +0.08 |
| dtfx_wick_fib | level=50-70 | US30 | 1h | trend | 33 | 55% | +0.329 | 1.8 | +0.57 | +0.17 | +0.77 | +0.32 | +0.21 | +0.15 |
| smc_displacement | disp_k=1.5 | XAUUSD | 15min | trend | 30 | 53% | +0.404 | 1.7 | +0.70 | +0.07 | +0.64 | +0.87 | -0.13 | +0.22 |
| london_breakout | min_body_atr=0.0 | EURUSD | 1h | trend | 40 | 65% | +0.218 | 1.7 | +0.05 | +0.39 | -0.21 | +0.37 | +0.33 | +0.45 |
| ict_amd | model=midnight | XAUUSD | 30min | std | 91 | 56% | +0.119 | 1.7 | +0.06 | +0.19 | -0.02 | +0.15 | +0.14 | +0.23 |
| trend_pullback | swing_bars=8 | NDQ | 15min | trend | 58 | 52% | +0.276 | 1.7 | +0.22 | +0.31 | -0.10 | +0.54 | +0.23 | +0.39 |
| smc_bos_retest | tol_atr=0.15 | EURUSD | 1h | trend | 36 | 56% | +0.220 | 1.6 | +0.08 | +0.35 | -0.05 | +0.15 | +0.23 | +0.41 |
| smc_liquidity_sweep | default | NDQ | 30min | trend | 33 | 55% | +0.309 | 1.6 | +0.48 | +0.14 | +0.43 | +0.55 | +0.33 | -0.12 |

211 cells qualify out of 2280 with ≥30 trades. With this many cells, a few will pass by luck alone — a t above ~3 is the bar for 'probably real'.

## 3 · Every setup, overall (default variant, all timeframes but 1m; std = 1R first target, trend = 2R first target, 15m+ only)

| setup | sym | exit | trades | win | avg R | first half | second half |
|---|---|---|---|---|---|---|---|
| dtfx_close_fib | AUDUSD | std | 77 | 25% | -0.367 | -0.41 | -0.33 |
| dtfx_close_fib | AUDUSD | trend | 77 | 21% | -0.455 | -0.53 | -0.39 |
| dtfx_close_fib | EURUSD | std | 62 | 47% | -0.010 | -0.07 | +0.05 |
| dtfx_close_fib | EURUSD | trend | 62 | 47% | +0.003 | +0.10 | -0.09 |
| dtfx_close_fib | GBPUSD | std | 55 | 38% | -0.185 | -0.26 | -0.12 |
| dtfx_close_fib | GBPUSD | trend | 55 | 29% | -0.151 | -0.31 | -0.02 |
| dtfx_close_fib | NDQ | std | 64 | 55% | +0.004 | -0.03 | +0.05 |
| dtfx_close_fib | NDQ | trend | 62 | 44% | -0.088 | -0.18 | +0.04 |
| dtfx_close_fib | US30 | std | 62 | 53% | +0.061 | +0.12 | -0.00 |
| dtfx_close_fib | US30 | trend | 61 | 44% | +0.055 | +0.16 | -0.05 |
| dtfx_close_fib | XAUUSD | std | 71 | 42% | -0.134 | -0.19 | -0.08 |
| dtfx_close_fib | XAUUSD | trend | 71 | 42% | -0.081 | -0.05 | -0.11 |
| dtfx_close_fib_brk | AUDUSD | std | 68 | 24% | -0.411 | -0.55 | -0.27 |
| dtfx_close_fib_brk | AUDUSD | trend | 68 | 22% | -0.497 | -0.62 | -0.37 |
| dtfx_close_fib_brk | EURUSD | std | 46 | 48% | -0.022 | +0.01 | -0.07 |
| dtfx_close_fib_brk | EURUSD | trend | 46 | 46% | +0.033 | +0.20 | -0.18 |
| dtfx_close_fib_brk | GBPUSD | std | 47 | 38% | -0.137 | -0.07 | -0.21 |
| dtfx_close_fib_brk | GBPUSD | trend | 47 | 36% | -0.094 | +0.00 | -0.19 |
| dtfx_close_fib_brk | NDQ | std | 40 | 60% | +0.152 | +0.16 | +0.14 |
| dtfx_close_fib_brk | NDQ | trend | 40 | 45% | +0.125 | +0.01 | +0.42 |
| dtfx_close_fib_brk | US30 | std | 51 | 51% | +0.033 | +0.17 | -0.12 |
| dtfx_close_fib_brk | US30 | trend | 51 | 45% | +0.087 | +0.39 | -0.25 |
| dtfx_close_fib_brk | XAUUSD | std | 57 | 46% | -0.123 | -0.18 | -0.06 |
| dtfx_close_fib_brk | XAUUSD | trend | 57 | 40% | -0.201 | -0.27 | -0.11 |
| dtfx_close_origin | AUDUSD | std | 67 | 39% | -0.219 | -0.25 | -0.19 |
| dtfx_close_origin | AUDUSD | trend | 66 | 35% | -0.257 | -0.42 | -0.11 |
| dtfx_close_origin | EURUSD | std | 62 | 50% | -0.080 | -0.17 | +0.00 |
| dtfx_close_origin | EURUSD | trend | 61 | 34% | -0.212 | -0.37 | -0.07 |
| dtfx_close_origin | GBPUSD | std | 53 | 53% | -0.015 | -0.05 | +0.01 |
| dtfx_close_origin | GBPUSD | trend | 53 | 40% | +0.027 | +0.06 | +0.00 |
| dtfx_close_origin | NDQ | std | 60 | 40% | -0.074 | -0.14 | -0.02 |
| dtfx_close_origin | NDQ | trend | 60 | 35% | -0.150 | -0.37 | +0.04 |
| dtfx_close_origin | US30 | std | 80 | 46% | -0.114 | -0.06 | -0.17 |
| dtfx_close_origin | US30 | trend | 80 | 44% | +0.078 | +0.15 | -0.00 |
| dtfx_close_origin | XAUUSD | std | 62 | 37% | -0.320 | -0.33 | -0.31 |
| dtfx_close_origin | XAUUSD | trend | 62 | 31% | -0.341 | -0.20 | -0.50 |
| dtfx_wick_fib | AUDUSD | std | 97 | 31% | -0.290 | -0.25 | -0.32 |
| dtfx_wick_fib | AUDUSD | trend | 96 | 27% | -0.316 | -0.35 | -0.29 |
| dtfx_wick_fib | EURUSD | std | 85 | 53% | +0.102 | +0.15 | +0.03 |
| dtfx_wick_fib | EURUSD | trend | 83 | 49% | +0.143 | +0.22 | +0.04 |
| dtfx_wick_fib | GBPUSD | std | 91 | 41% | -0.146 | -0.09 | -0.19 |
| dtfx_wick_fib | GBPUSD | trend | 91 | 30% | -0.165 | -0.09 | -0.23 |
| dtfx_wick_fib | NDQ | std | 104 | 56% | -0.039 | -0.15 | +0.10 |
| dtfx_wick_fib | NDQ | trend | 102 | 44% | -0.071 | -0.23 | +0.13 |
| dtfx_wick_fib | US30 | std | 77 | 52% | -0.050 | +0.04 | -0.12 |
| dtfx_wick_fib | US30 | trend | 75 | 37% | -0.153 | -0.01 | -0.28 |
| dtfx_wick_fib | XAUUSD | std | 114 | 49% | -0.013 | -0.02 | -0.00 |
| dtfx_wick_fib | XAUUSD | trend | 113 | 49% | +0.080 | +0.17 | -0.01 |
| dtfx_zone | AUDUSD | std | 255 | 43% | -0.093 | -0.08 | -0.10 |
| dtfx_zone | AUDUSD | trend | 247 | 37% | -0.169 | -0.18 | -0.15 |
| dtfx_zone | EURUSD | std | 242 | 39% | -0.185 | -0.25 | -0.10 |
| dtfx_zone | EURUSD | trend | 233 | 33% | -0.233 | -0.34 | -0.09 |
| dtfx_zone | GBPUSD | std | 232 | 47% | -0.044 | -0.07 | -0.02 |
| dtfx_zone | GBPUSD | trend | 222 | 38% | -0.065 | -0.08 | -0.05 |
| dtfx_zone | NDQ | std | 214 | 52% | +0.024 | +0.01 | +0.03 |
| dtfx_zone | NDQ | trend | 211 | 45% | -0.007 | +0.00 | -0.02 |
| dtfx_zone | US30 | std | 219 | 44% | -0.108 | -0.17 | -0.04 |
| dtfx_zone | US30 | trend | 214 | 37% | -0.030 | -0.06 | +0.00 |
| dtfx_zone | XAUUSD | std | 226 | 48% | -0.048 | -0.04 | -0.06 |
| dtfx_zone | XAUUSD | trend | 221 | 46% | -0.014 | +0.01 | -0.03 |
| ict_2022 | AUDUSD | std | 25 | 52% | -0.074 | -0.09 | -0.05 |
| ict_2022 | AUDUSD | trend | 25 | 32% | -0.068 | -0.15 | +0.03 |
| ict_2022 | EURUSD | std | 40 | 42% | -0.167 | -0.24 | -0.06 |
| ict_2022 | EURUSD | trend | 40 | 30% | -0.195 | -0.40 | +0.11 |
| ict_2022 | GBPUSD | std | 45 | 56% | +0.136 | +0.13 | +0.14 |
| ict_2022 | GBPUSD | trend | 45 | 36% | -0.061 | -0.15 | +0.06 |
| ict_2022 | NDQ | std | 30 | 53% | +0.055 | -0.03 | +0.11 |
| ict_2022 | NDQ | trend | 30 | 40% | -0.121 | -0.26 | -0.03 |
| ict_2022 | US30 | std | 34 | 56% | +0.063 | -0.17 | +0.27 |
| ict_2022 | US30 | trend | 34 | 41% | -0.048 | -0.22 | +0.10 |
| ict_2022 | XAUUSD | std | 25 | 56% | +0.165 | +0.15 | +0.17 |
| ict_2022 | XAUUSD | trend | 25 | 52% | +0.326 | +0.46 | +0.24 |
| ict_amd | AUDUSD | std | 80 | 45% | +0.012 | -0.07 | +0.13 |
| ict_amd | AUDUSD | trend | 80 | 41% | +0.014 | -0.11 | +0.19 |
| ict_amd | EURUSD | std | 140 | 47% | -0.038 | +0.00 | -0.10 |
| ict_amd | EURUSD | trend | 140 | 42% | -0.025 | -0.08 | +0.06 |
| ict_amd | GBPUSD | std | 140 | 46% | +0.071 | +0.02 | +0.15 |
| ict_amd | GBPUSD | trend | 140 | 43% | +0.099 | +0.00 | +0.26 |
| ict_amd | NDQ | std | 123 | 46% | -0.012 | -0.04 | +0.02 |
| ict_amd | NDQ | trend | 123 | 46% | +0.047 | -0.06 | +0.18 |
| ict_amd | US30 | std | 175 | 45% | -0.059 | +0.02 | -0.13 |
| ict_amd | US30 | trend | 175 | 29% | -0.236 | -0.11 | -0.36 |
| ict_amd | XAUUSD | std | 77 | 55% | +0.087 | +0.08 | +0.11 |
| ict_amd | XAUUSD | trend | 77 | 58% | +0.070 | +0.05 | +0.11 |
| ict_fvg_sweep | AUDUSD | std | 51 | 47% | +0.037 | +0.11 | -0.04 |
| ict_fvg_sweep | AUDUSD | trend | 51 | 45% | +0.072 | +0.20 | -0.07 |
| ict_fvg_sweep | EURUSD | std | 50 | 32% | -0.333 | -0.40 | -0.26 |
| ict_fvg_sweep | EURUSD | trend | 50 | 24% | -0.343 | -0.49 | -0.17 |
| ict_fvg_sweep | GBPUSD | std | 52 | 52% | +0.003 | -0.04 | +0.07 |
| ict_fvg_sweep | GBPUSD | trend | 52 | 35% | -0.155 | -0.22 | -0.06 |
| ict_fvg_sweep | NDQ | std | 38 | 39% | -0.351 | -0.65 | -0.20 |
| ict_fvg_sweep | NDQ | trend | 37 | 22% | -0.510 | -0.91 | -0.32 |
| ict_fvg_sweep | US30 | std | 49 | 57% | +0.200 | -0.18 | +0.66 |
| ict_fvg_sweep | US30 | trend | 48 | 40% | -0.029 | -0.39 | +0.44 |
| ict_fvg_sweep | XAUUSD | std | 36 | 56% | +0.234 | +0.27 | +0.18 |
| ict_fvg_sweep | XAUUSD | trend | 36 | 44% | +0.221 | +0.28 | +0.15 |
| ict_ote | AUDUSD | std | 241 | 46% | -0.114 | -0.09 | -0.14 |
| ict_ote | AUDUSD | trend | 233 | 35% | -0.173 | -0.15 | -0.20 |
| ict_ote | EURUSD | std | 229 | 39% | -0.251 | -0.29 | -0.22 |
| ict_ote | EURUSD | trend | 224 | 30% | -0.267 | -0.36 | -0.18 |
| ict_ote | GBPUSD | std | 244 | 48% | -0.032 | -0.08 | +0.02 |
| ict_ote | GBPUSD | trend | 237 | 36% | -0.048 | -0.02 | -0.08 |
| ict_ote | NDQ | std | 207 | 54% | -0.015 | -0.18 | +0.10 |
| ict_ote | NDQ | trend | 203 | 40% | -0.016 | -0.06 | +0.01 |
| ict_ote | US30 | std | 202 | 50% | +0.010 | +0.01 | +0.01 |
| ict_ote | US30 | trend | 200 | 42% | +0.119 | +0.01 | +0.21 |
| ict_ote | XAUUSD | std | 187 | 49% | -0.073 | -0.15 | +0.01 |
| ict_ote | XAUUSD | trend | 184 | 40% | -0.070 | -0.11 | -0.03 |
| ict_silver_bullet | AUDUSD | std | 13 | 38% | +0.037 | +0.59 | -0.61 |
| ict_silver_bullet | AUDUSD | trend | 13 | 46% | +0.089 | +0.70 | -0.63 |
| ict_silver_bullet | EURUSD | std | 7 | 71% | +0.443 | -0.30 | +0.74 |
| ict_silver_bullet | EURUSD | trend | 7 | 43% | +0.155 | -1.00 | +0.62 |
| ict_silver_bullet | GBPUSD | std | 9 | 44% | -0.136 | +0.39 | -0.79 |
| ict_silver_bullet | GBPUSD | trend | 9 | 33% | -0.093 | +0.40 | -0.71 |
| ict_silver_bullet | NDQ | std | 20 | 45% | +0.072 | +0.20 | -0.11 |
| ict_silver_bullet | NDQ | trend | 20 | 45% | +0.050 | +0.27 | -0.28 |
| ict_silver_bullet | US30 | std | 16 | 50% | -0.056 | -0.01 | -0.15 |
| ict_silver_bullet | US30 | trend | 16 | 50% | -0.002 | +0.15 | -0.34 |
| ict_silver_bullet | XAUUSD | std | 3 | 33% | -0.072 | -0.07 | — |
| ict_silver_bullet | XAUUSD | trend | 3 | 33% | +0.169 | +0.17 | — |
| ict_turtle_soup | AUDUSD | std | 339 | 44% | -0.131 | -0.03 | -0.24 |
| ict_turtle_soup | AUDUSD | trend | 339 | 37% | -0.083 | -0.03 | -0.14 |
| ict_turtle_soup | EURUSD | std | 354 | 46% | -0.063 | -0.10 | -0.01 |
| ict_turtle_soup | EURUSD | trend | 352 | 35% | -0.054 | -0.15 | +0.07 |
| ict_turtle_soup | GBPUSD | std | 387 | 45% | -0.044 | +0.02 | -0.14 |
| ict_turtle_soup | GBPUSD | trend | 386 | 34% | -0.030 | +0.09 | -0.19 |
| ict_turtle_soup | NDQ | std | 405 | 48% | +0.015 | +0.03 | -0.01 |
| ict_turtle_soup | NDQ | trend | 404 | 38% | +0.009 | +0.04 | -0.02 |
| ict_turtle_soup | US30 | std | 413 | 46% | -0.101 | -0.09 | -0.11 |
| ict_turtle_soup | US30 | trend | 413 | 34% | -0.093 | -0.10 | -0.09 |
| ict_turtle_soup | XAUUSD | std | 364 | 50% | -0.020 | -0.02 | -0.02 |
| ict_turtle_soup | XAUUSD | trend | 361 | 38% | -0.072 | -0.02 | -0.12 |
| london_breakout | AUDUSD | std | 101 | 45% | -0.086 | -0.30 | +0.07 |
| london_breakout | AUDUSD | trend | 101 | 48% | +0.102 | -0.30 | +0.40 |
| london_breakout | EURUSD | std | 155 | 50% | -0.012 | -0.08 | +0.05 |
| london_breakout | EURUSD | trend | 155 | 48% | +0.055 | -0.20 | +0.31 |
| london_breakout | GBPUSD | std | 166 | 48% | +0.019 | -0.06 | +0.13 |
| london_breakout | GBPUSD | trend | 166 | 40% | -0.032 | -0.24 | +0.26 |
| london_breakout | NDQ | std | 105 | 42% | -0.112 | -0.24 | +0.01 |
| london_breakout | NDQ | trend | 105 | 38% | -0.023 | -0.38 | +0.32 |
| london_breakout | US30 | std | 140 | 44% | -0.127 | -0.25 | -0.03 |
| london_breakout | US30 | trend | 140 | 27% | -0.232 | -0.37 | -0.12 |
| london_breakout | XAUUSD | std | 81 | 43% | -0.003 | -0.01 | +0.00 |
| london_breakout | XAUUSD | trend | 81 | 48% | +0.185 | -0.11 | +0.38 |
| macd_cross | AUDUSD | std | 113 | 47% | -0.046 | -0.06 | -0.03 |
| macd_cross | AUDUSD | trend | 110 | 46% | +0.068 | -0.07 | +0.20 |
| macd_cross | EURUSD | std | 126 | 54% | +0.021 | +0.08 | -0.04 |
| macd_cross | EURUSD | trend | 123 | 44% | +0.080 | +0.11 | +0.05 |
| macd_cross | GBPUSD | std | 123 | 47% | +0.034 | +0.01 | +0.06 |
| macd_cross | GBPUSD | trend | 122 | 41% | +0.011 | -0.02 | +0.05 |
| macd_cross | NDQ | std | 121 | 48% | -0.013 | +0.02 | -0.04 |
| macd_cross | NDQ | trend | 119 | 50% | +0.114 | +0.13 | +0.10 |
| macd_cross | US30 | std | 105 | 51% | -0.044 | -0.05 | -0.03 |
| macd_cross | US30 | trend | 104 | 41% | -0.082 | -0.25 | +0.14 |
| macd_cross | XAUUSD | std | 134 | 39% | -0.118 | -0.06 | -0.18 |
| macd_cross | XAUUSD | trend | 127 | 35% | -0.170 | -0.10 | -0.24 |
| rsi_pullback | AUDUSD | std | 110 | 60% | +0.044 | +0.20 | -0.06 |
| rsi_pullback | AUDUSD | trend | 109 | 47% | +0.140 | +0.48 | -0.08 |
| rsi_pullback | EURUSD | std | 122 | 46% | -0.042 | +0.10 | -0.16 |
| rsi_pullback | EURUSD | trend | 122 | 39% | -0.052 | +0.14 | -0.21 |
| rsi_pullback | GBPUSD | std | 119 | 39% | -0.220 | -0.31 | -0.13 |
| rsi_pullback | GBPUSD | trend | 119 | 31% | -0.143 | -0.18 | -0.10 |
| rsi_pullback | NDQ | std | 146 | 48% | -0.033 | +0.08 | -0.11 |
| rsi_pullback | NDQ | trend | 145 | 46% | +0.063 | +0.19 | -0.02 |
| rsi_pullback | US30 | std | 111 | 45% | -0.119 | -0.17 | -0.07 |
| rsi_pullback | US30 | trend | 111 | 32% | -0.130 | -0.18 | -0.07 |
| rsi_pullback | XAUUSD | std | 130 | 64% | +0.219 | +0.16 | +0.28 |
| rsi_pullback | XAUUSD | trend | 128 | 50% | +0.232 | +0.17 | +0.29 |
| smc_bos_retest | AUDUSD | std | 255 | 38% | -0.158 | -0.15 | -0.17 |
| smc_bos_retest | AUDUSD | trend | 244 | 32% | -0.218 | -0.23 | -0.20 |
| smc_bos_retest | EURUSD | std | 213 | 45% | -0.022 | -0.04 | -0.01 |
| smc_bos_retest | EURUSD | trend | 198 | 45% | +0.064 | -0.00 | +0.12 |
| smc_bos_retest | GBPUSD | std | 210 | 46% | -0.013 | +0.04 | -0.05 |
| smc_bos_retest | GBPUSD | trend | 198 | 41% | -0.026 | +0.06 | -0.09 |
| smc_bos_retest | NDQ | std | 245 | 48% | -0.022 | -0.10 | +0.04 |
| smc_bos_retest | NDQ | trend | 231 | 45% | +0.018 | -0.16 | +0.17 |
| smc_bos_retest | US30 | std | 232 | 44% | -0.137 | -0.19 | -0.09 |
| smc_bos_retest | US30 | trend | 217 | 36% | -0.164 | -0.13 | -0.20 |
| smc_bos_retest | XAUUSD | std | 264 | 51% | +0.029 | +0.08 | -0.02 |
| smc_bos_retest | XAUUSD | trend | 242 | 51% | +0.112 | +0.16 | +0.06 |
| smc_breaker | AUDUSD | std | 104 | 37% | -0.245 | -0.32 | -0.12 |
| smc_breaker | AUDUSD | trend | 104 | 23% | -0.317 | -0.49 | -0.05 |
| smc_breaker | EURUSD | std | 90 | 39% | -0.207 | -0.13 | -0.29 |
| smc_breaker | EURUSD | trend | 90 | 31% | -0.137 | -0.00 | -0.28 |
| smc_breaker | GBPUSD | std | 109 | 47% | -0.129 | -0.03 | -0.23 |
| smc_breaker | GBPUSD | trend | 109 | 31% | -0.145 | -0.09 | -0.19 |
| smc_breaker | NDQ | std | 89 | 45% | -0.130 | -0.27 | +0.03 |
| smc_breaker | NDQ | trend | 88 | 39% | -0.041 | -0.06 | -0.02 |
| smc_breaker | US30 | std | 98 | 47% | -0.076 | -0.19 | +0.04 |
| smc_breaker | US30 | trend | 98 | 39% | -0.044 | -0.26 | +0.17 |
| smc_breaker | XAUUSD | std | 99 | 51% | +0.036 | -0.08 | +0.11 |
| smc_breaker | XAUUSD | trend | 99 | 42% | +0.038 | -0.11 | +0.13 |
| smc_choch | AUDUSD | std | 233 | 40% | -0.141 | -0.11 | -0.17 |
| smc_choch | AUDUSD | trend | 230 | 37% | -0.116 | -0.18 | -0.06 |
| smc_choch | EURUSD | std | 208 | 45% | -0.054 | -0.15 | +0.03 |
| smc_choch | EURUSD | trend | 206 | 42% | -0.039 | -0.18 | +0.08 |
| smc_choch | GBPUSD | std | 235 | 45% | -0.076 | -0.00 | -0.15 |
| smc_choch | GBPUSD | trend | 235 | 39% | -0.021 | -0.03 | -0.01 |
| smc_choch | NDQ | std | 191 | 50% | -0.014 | -0.04 | +0.01 |
| smc_choch | NDQ | trend | 191 | 47% | +0.011 | -0.09 | +0.09 |
| smc_choch | US30 | std | 206 | 48% | -0.052 | -0.08 | -0.03 |
| smc_choch | US30 | trend | 205 | 36% | -0.072 | -0.14 | -0.01 |
| smc_choch | XAUUSD | std | 216 | 48% | -0.004 | +0.04 | -0.04 |
| smc_choch | XAUUSD | trend | 212 | 40% | -0.071 | -0.05 | -0.09 |
| smc_displacement | AUDUSD | std | 106 | 37% | -0.236 | -0.18 | -0.29 |
| smc_displacement | AUDUSD | trend | 106 | 27% | -0.340 | -0.35 | -0.33 |
| smc_displacement | EURUSD | std | 101 | 40% | -0.213 | -0.32 | -0.10 |
| smc_displacement | EURUSD | trend | 101 | 27% | -0.234 | -0.33 | -0.13 |
| smc_displacement | GBPUSD | std | 99 | 45% | -0.073 | -0.09 | -0.06 |
| smc_displacement | GBPUSD | trend | 96 | 40% | +0.045 | -0.03 | +0.11 |
| smc_displacement | NDQ | std | 66 | 50% | -0.008 | -0.07 | +0.06 |
| smc_displacement | NDQ | trend | 65 | 40% | -0.021 | -0.36 | +0.33 |
| smc_displacement | US30 | std | 68 | 53% | +0.003 | +0.02 | -0.02 |
| smc_displacement | US30 | trend | 67 | 34% | -0.187 | -0.21 | -0.17 |
| smc_displacement | XAUUSD | std | 81 | 60% | +0.147 | +0.33 | -0.04 |
| smc_displacement | XAUUSD | trend | 81 | 51% | +0.240 | +0.49 | -0.03 |
| smc_ifvg | AUDUSD | std | 300 | 37% | -0.280 | -0.16 | -0.40 |
| smc_ifvg | AUDUSD | trend | 297 | 27% | -0.302 | -0.26 | -0.34 |
| smc_ifvg | EURUSD | std | 309 | 48% | -0.050 | -0.06 | -0.04 |
| smc_ifvg | EURUSD | trend | 306 | 38% | +0.023 | -0.03 | +0.08 |
| smc_ifvg | GBPUSD | std | 259 | 42% | -0.171 | -0.18 | -0.16 |
| smc_ifvg | GBPUSD | trend | 259 | 31% | -0.159 | -0.17 | -0.14 |
| smc_ifvg | NDQ | std | 240 | 48% | -0.068 | -0.16 | +0.01 |
| smc_ifvg | NDQ | trend | 238 | 36% | -0.053 | -0.14 | +0.02 |
| smc_ifvg | US30 | std | 234 | 47% | -0.072 | -0.04 | -0.11 |
| smc_ifvg | US30 | trend | 232 | 34% | -0.052 | -0.06 | -0.04 |
| smc_ifvg | XAUUSD | std | 276 | 57% | +0.119 | +0.09 | +0.15 |
| smc_ifvg | XAUUSD | trend | 270 | 43% | +0.109 | +0.05 | +0.17 |
| smc_liquidity_sweep | AUDUSD | std | 95 | 42% | -0.134 | -0.16 | -0.10 |
| smc_liquidity_sweep | AUDUSD | trend | 95 | 40% | -0.120 | -0.22 | -0.01 |
| smc_liquidity_sweep | EURUSD | std | 130 | 49% | -0.011 | +0.07 | -0.15 |
| smc_liquidity_sweep | EURUSD | trend | 130 | 42% | -0.011 | -0.04 | +0.04 |
| smc_liquidity_sweep | GBPUSD | std | 133 | 47% | +0.008 | +0.11 | -0.15 |
| smc_liquidity_sweep | GBPUSD | trend | 133 | 39% | +0.016 | +0.04 | -0.02 |
| smc_liquidity_sweep | NDQ | std | 105 | 49% | +0.032 | +0.10 | -0.05 |
| smc_liquidity_sweep | NDQ | trend | 105 | 50% | +0.188 | +0.28 | +0.09 |
| smc_liquidity_sweep | US30 | std | 129 | 50% | +0.057 | +0.13 | -0.02 |
| smc_liquidity_sweep | US30 | trend | 129 | 33% | -0.098 | +0.04 | -0.24 |
| smc_liquidity_sweep | XAUUSD | std | 76 | 57% | +0.042 | -0.13 | +0.22 |
| smc_liquidity_sweep | XAUUSD | trend | 76 | 51% | +0.021 | -0.12 | +0.17 |
| smc_mss | AUDUSD | std | 80 | 39% | -0.083 | -0.16 | -0.02 |
| smc_mss | AUDUSD | trend | 77 | 44% | +0.046 | -0.04 | +0.11 |
| smc_mss | EURUSD | std | 86 | 52% | +0.014 | -0.15 | +0.22 |
| smc_mss | EURUSD | trend | 86 | 47% | +0.022 | -0.23 | +0.34 |
| smc_mss | GBPUSD | std | 113 | 47% | -0.007 | -0.01 | -0.01 |
| smc_mss | GBPUSD | trend | 111 | 37% | +0.002 | -0.08 | +0.09 |
| smc_mss | NDQ | std | 84 | 45% | -0.050 | -0.01 | -0.07 |
| smc_mss | NDQ | trend | 84 | 44% | +0.046 | +0.15 | -0.02 |
| smc_mss | US30 | std | 87 | 52% | +0.052 | -0.13 | +0.22 |
| smc_mss | US30 | trend | 87 | 39% | -0.084 | -0.32 | +0.14 |
| smc_mss | XAUUSD | std | 77 | 53% | +0.025 | +0.09 | -0.05 |
| smc_mss | XAUUSD | trend | 77 | 51% | +0.021 | +0.03 | +0.01 |
| smc_order_block | AUDUSD | std | 191 | 38% | -0.283 | -0.25 | -0.32 |
| smc_order_block | AUDUSD | trend | 188 | 25% | -0.334 | -0.38 | -0.29 |
| smc_order_block | EURUSD | std | 179 | 44% | -0.135 | -0.15 | -0.11 |
| smc_order_block | EURUSD | trend | 177 | 36% | -0.047 | -0.18 | +0.11 |
| smc_order_block | GBPUSD | std | 187 | 47% | -0.108 | -0.09 | -0.12 |
| smc_order_block | GBPUSD | trend | 187 | 34% | -0.056 | +0.03 | -0.12 |
| smc_order_block | NDQ | std | 175 | 50% | -0.056 | -0.16 | +0.01 |
| smc_order_block | NDQ | trend | 174 | 35% | -0.081 | -0.19 | -0.01 |
| smc_order_block | US30 | std | 157 | 47% | -0.042 | -0.10 | +0.01 |
| smc_order_block | US30 | trend | 157 | 34% | -0.043 | -0.19 | +0.10 |
| smc_order_block | XAUUSD | std | 176 | 42% | -0.160 | -0.18 | -0.15 |
| smc_order_block | XAUUSD | trend | 175 | 31% | -0.155 | -0.22 | -0.09 |
| smt_divergence | NDQ | std | 88 | 52% | +0.086 | +0.22 | -0.02 |
| smt_divergence | NDQ | trend | 88 | 44% | +0.128 | +0.31 | -0.01 |
| smt_divergence | US30 | std | 107 | 46% | -0.141 | -0.02 | -0.24 |
| smt_divergence | US30 | trend | 106 | 28% | -0.306 | -0.25 | -0.35 |
| sr_rejection | AUDUSD | std | 526 | 42% | -0.189 | -0.18 | -0.20 |
| sr_rejection | AUDUSD | trend | 499 | 31% | -0.169 | -0.17 | -0.17 |
| sr_rejection | EURUSD | std | 486 | 44% | -0.128 | -0.07 | -0.18 |
| sr_rejection | EURUSD | trend | 475 | 35% | -0.054 | -0.03 | -0.08 |
| sr_rejection | GBPUSD | std | 492 | 39% | -0.233 | -0.25 | -0.21 |
| sr_rejection | GBPUSD | trend | 490 | 29% | -0.206 | -0.21 | -0.20 |
| sr_rejection | NDQ | std | 453 | 48% | -0.016 | -0.08 | +0.04 |
| sr_rejection | NDQ | trend | 440 | 36% | -0.043 | -0.09 | -0.00 |
| sr_rejection | US30 | std | 432 | 45% | -0.055 | -0.04 | -0.07 |
| sr_rejection | US30 | trend | 421 | 36% | -0.010 | -0.08 | +0.06 |
| sr_rejection | XAUUSD | std | 581 | 50% | -0.009 | +0.01 | -0.03 |
| sr_rejection | XAUUSD | trend | 564 | 36% | -0.053 | +0.03 | -0.15 |
| stoic_sbs | AUDUSD | std | 20 | 45% | +0.008 | +0.07 | -0.07 |
| stoic_sbs | AUDUSD | trend | 20 | 45% | +0.200 | +0.19 | +0.22 |
| stoic_sbs | EURUSD | std | 15 | 47% | -0.241 | -0.07 | -0.33 |
| stoic_sbs | EURUSD | trend | 15 | 33% | -0.216 | -0.70 | +0.03 |
| stoic_sbs | GBPUSD | std | 17 | 53% | +0.028 | +0.21 | -0.13 |
| stoic_sbs | GBPUSD | trend | 17 | 41% | -0.082 | +0.01 | -0.17 |
| stoic_sbs | NDQ | std | 10 | 30% | -0.566 | -0.83 | -0.30 |
| stoic_sbs | NDQ | trend | 10 | 20% | -0.769 | -1.00 | -0.54 |
| stoic_sbs | US30 | std | 7 | 29% | -0.373 | -0.60 | -0.06 |
| stoic_sbs | US30 | trend | 7 | 14% | -0.592 | -1.00 | -0.05 |
| stoic_sbs | XAUUSD | std | 9 | 78% | +0.127 | +0.40 | -0.09 |
| stoic_sbs | XAUUSD | trend | 9 | 67% | +0.016 | +0.21 | -0.14 |
| trend_breakout | AUDUSD | std | 337 | 40% | -0.193 | -0.24 | -0.15 |
| trend_breakout | AUDUSD | trend | 334 | 31% | -0.169 | -0.31 | -0.03 |
| trend_breakout | EURUSD | std | 261 | 40% | -0.094 | -0.12 | -0.07 |
| trend_breakout | EURUSD | trend | 261 | 32% | -0.095 | -0.12 | -0.07 |
| trend_breakout | GBPUSD | std | 282 | 43% | -0.118 | -0.05 | -0.19 |
| trend_breakout | GBPUSD | trend | 281 | 33% | -0.097 | -0.05 | -0.15 |
| trend_breakout | NDQ | std | 279 | 51% | +0.015 | +0.00 | +0.03 |
| trend_breakout | NDQ | trend | 274 | 42% | +0.049 | +0.01 | +0.09 |
| trend_breakout | US30 | std | 235 | 50% | -0.019 | -0.02 | -0.02 |
| trend_breakout | US30 | trend | 231 | 39% | +0.005 | +0.08 | -0.07 |
| trend_breakout | XAUUSD | std | 255 | 53% | +0.073 | +0.14 | +0.01 |
| trend_breakout | XAUUSD | trend | 254 | 43% | +0.102 | +0.14 | +0.07 |
| trend_pullback | AUDUSD | std | 130 | 45% | -0.121 | -0.21 | -0.01 |
| trend_pullback | AUDUSD | trend | 125 | 35% | -0.162 | -0.26 | -0.05 |
| trend_pullback | EURUSD | std | 128 | 41% | -0.171 | -0.10 | -0.23 |
| trend_pullback | EURUSD | trend | 124 | 31% | -0.182 | -0.14 | -0.22 |
| trend_pullback | GBPUSD | std | 152 | 48% | -0.035 | -0.01 | -0.06 |
| trend_pullback | GBPUSD | trend | 148 | 34% | -0.093 | -0.09 | -0.10 |
| trend_pullback | NDQ | std | 133 | 59% | +0.096 | -0.12 | +0.24 |
| trend_pullback | NDQ | trend | 129 | 49% | +0.166 | -0.08 | +0.34 |
| trend_pullback | US30 | std | 128 | 43% | -0.137 | -0.24 | -0.02 |
| trend_pullback | US30 | trend | 124 | 36% | -0.041 | -0.18 | +0.11 |
| trend_pullback | XAUUSD | std | 104 | 46% | -0.059 | +0.04 | -0.20 |
| trend_pullback | XAUUSD | trend | 103 | 42% | -0.066 | +0.21 | -0.44 |
| vwap | AUDUSD | std | 372 | 42% | -0.148 | -0.10 | -0.20 |
| vwap | AUDUSD | trend | 343 | 32% | -0.178 | -0.18 | -0.17 |
| vwap | EURUSD | std | 382 | 44% | -0.157 | -0.19 | -0.13 |
| vwap | EURUSD | trend | 369 | 32% | -0.160 | -0.25 | -0.07 |
| vwap | GBPUSD | std | 346 | 42% | -0.169 | -0.09 | -0.25 |
| vwap | GBPUSD | trend | 333 | 30% | -0.195 | -0.18 | -0.21 |
| vwap | NDQ | std | 301 | 51% | +0.002 | -0.13 | +0.09 |
| vwap | NDQ | trend | 288 | 40% | +0.030 | -0.20 | +0.20 |
| vwap | US30 | std | 375 | 47% | +0.010 | -0.07 | +0.08 |
| vwap | US30 | trend | 366 | 34% | -0.070 | -0.19 | +0.02 |
| vwap | XAUUSD | std | 323 | 54% | +0.104 | +0.08 | +0.14 |
| vwap | XAUUSD | trend | 306 | 41% | +0.128 | +0.07 | +0.21 |
| zone_confluence | AUDUSD | std | 144 | 44% | -0.115 | -0.14 | -0.08 |
| zone_confluence | AUDUSD | trend | 143 | 32% | -0.192 | -0.24 | -0.14 |
| zone_confluence | EURUSD | std | 168 | 46% | -0.147 | -0.21 | -0.08 |
| zone_confluence | EURUSD | trend | 163 | 34% | -0.165 | -0.33 | +0.02 |
| zone_confluence | GBPUSD | std | 164 | 48% | -0.069 | -0.08 | -0.06 |
| zone_confluence | GBPUSD | trend | 162 | 36% | -0.102 | -0.08 | -0.12 |
| zone_confluence | NDQ | std | 151 | 50% | -0.104 | -0.19 | -0.04 |
| zone_confluence | NDQ | trend | 148 | 33% | -0.213 | -0.20 | -0.22 |
| zone_confluence | US30 | std | 148 | 45% | +0.001 | -0.11 | +0.13 |
| zone_confluence | US30 | trend | 145 | 42% | +0.049 | -0.09 | +0.21 |
| zone_confluence | XAUUSD | std | 133 | 50% | -0.014 | -0.03 | -0.00 |
| zone_confluence | XAUUSD | trend | 130 | 39% | -0.107 | -0.05 | -0.15 |

## 4 · Best cell per setup (≥30 trades, by t-stat)

| setup | variant | sym | tf | exit | trades | win | avg R | t | quarters positive |
|---|---|---|---|---|---|---|---|---|---|
| smc_displacement | disp_k=1.0 | XAUUSD | 15min | std | 68 | 68% | +0.295 | 2.6 | 4/4 |
| vwap | vol=dry | XAUUSD | 15min | trend | 83 | 48% | +0.406 | 2.6 | 4/4 |
| rsi_pullback | default | XAUUSD | 15min | std | 79 | 63% | +0.264 | 2.4 | 3/4 |
| trend_breakout | vol=impulse | US30 | 15min | trend | 33 | 58% | +0.651 | 2.4 | 4/4 |
| ict_turtle_soup | level=session | US30 | 15min | trend | 62 | 48% | +0.443 | 2.3 | 4/4 |
| smc_ifvg | default | XAUUSD | 15min | std | 154 | 60% | +0.175 | 2.2 | 3/4 |
| sr_rejection | default | NDQ | 30min | trend | 117 | 48% | +0.269 | 2.1 | 4/4 |
| dtfx_zone | default | NDQ | 30min | std | 55 | 64% | +0.175 | 2.1 | 3/4 |
| smc_choch | swing=2 | NDQ | 1h | trend | 38 | 61% | +0.240 | 2.0 | 4/4 |
| smc_bos_retest | stop=level | EURUSD | 1h | std | 37 | 54% | +0.206 | 2.0 | 4/4 |
| dtfx_wick_fib | level=50-70 | NDQ | 1h | trend | 36 | 67% | +0.267 | 1.9 | 3/4 |
| london_breakout | min_body_atr=0.0 | EURUSD | 1h | trend | 40 | 65% | +0.218 | 1.7 | 3/4 |
| dtfx_close_fib | level=0.3 | XAUUSD | 1h | std | 30 | 73% | +0.113 | 1.7 | 3/4 |
| ict_amd | model=midnight | XAUUSD | 30min | trend | 91 | 52% | +0.183 | 1.7 | 2/4 |
| trend_pullback | swing_bars=8 | NDQ | 15min | trend | 58 | 52% | +0.276 | 1.7 | 3/4 |
| smc_liquidity_sweep | default | NDQ | 30min | trend | 33 | 55% | +0.309 | 1.6 | 3/4 |
| macd_cross | default | NDQ | 15min | trend | 68 | 47% | +0.237 | 1.5 | 4/4 |
| dtfx_close_fib_brk | level=0.3 | NDQ | 15min | trend | 45 | 49% | +0.257 | 1.4 | 3/4 |
| ict_ote | default | US30 | 30min | trend | 58 | 45% | +0.256 | 1.3 | 2/4 |
| smt_divergence | confirm=reclaim | US30 | 1h | std | 39 | 59% | +0.236 | 1.3 | 4/4 |
| dtfx_close_origin | confirm=touch | XAUUSD | 1h | trend | 52 | 50% | +0.194 | 1.2 | 3/4 |
| smc_mss | sweep_bars=10 | XAUUSD | 15min | std | 34 | 65% | +0.151 | 1.2 | 3/4 |
| smc_order_block | default | US30 | 30min | trend | 45 | 47% | +0.222 | 1.1 | 3/4 |
| zone_confluence | within=4 | US30 | 30min | trend | 45 | 44% | +0.171 | 0.9 | 2/4 |
| ict_2022 | discount=False | US30 | 15min | std | 48 | 60% | +0.100 | 0.7 | 2/4 |
| smc_breaker | default | US30 | 15min | trend | 61 | 41% | +0.087 | 0.5 | 2/4 |
| ict_silver_bullet | require_sweep=False | AUDUSD | 15min | trend | 34 | 38% | -0.007 | -0.0 | 1/4 |
