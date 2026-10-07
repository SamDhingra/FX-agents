# Strategy test — 365 days · costs oanda · 15min 30min 1h · tf15_oanda

Created 2026-10-06 20:49 NY · trades 2025-10-06 → 2026-10-06 · 220,334 simulated trades · 5,376 cells

R is per trade in units of its own risk, after spread. Quarters split the period in four equal parts; an edge worth trading is positive in most quarters, not just on average. 1-minute cells are listed but the playbook doesn't trade 1m (spread is too large a share of the bar).

## 1 · The playbook system, replayed week by week on unseen data

Each week: pick cells from the trailing 60 days, trade them the next week, capacity rules on. This is the number that says whether the approach works.

- trades **612**, win rate **47%**, avg **-0.042R**, total **-25.93R**, profit factor 0.89, worst drawdown -35.89R, t-stat -1.23, chance it's really ≤0: 0.887
- without the 3 best trades: -33.46R
- XAUUSD: 429 trades, 47% win, -6.02R
- GBPUSD: 68 trades, 38% win, -20.77R
- EURUSD: 63 trades, 44% win, -6.39R
- NDQ: 52 trades, 64% win, +7.26R

By month (R): 2025-11 -1.1 (5) · 2025-12 -15.7 (57) · 2026-01 -0.7 (18) · 2026-02 -7.6 (29) · 2026-03 -1.9 (48) · 2026-04 +8.2 (55) · 2026-05 -3.4 (65) · 2026-06 +11.7 (149) · 2026-07 -14.8 (81) · 2026-08 -10.2 (64) · 2026-09 +7.2 (36) · 2026-10 +0.0 (5)

Positive weeks: 19 of 45

## 2 · Cells that held up (≥30 trades, positive in both halves and ≥3 of 4 quarters)

| setup | variant | sym | tf | exit | trades | win | avg R | t | H1 | H2 | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| smc_displacement | disp_k=1.0 | XAUUSD | 15min | std | 67 | 66% | +0.279 | 2.5 | +0.37 | +0.13 | +0.29 | +0.49 | +0.06 | +0.23 |
| vwap | vol=dry | XAUUSD | 15min | std | 84 | 61% | +0.319 | 2.5 | +0.34 | +0.30 | +0.21 | +0.45 | +0.45 | +0.18 |
| trend_breakout | vol=impulse | US30 | 15min | trend | 33 | 58% | +0.654 | 2.5 | +0.95 | +0.38 | +1.00 | +0.90 | +0.66 | +0.18 |
| vwap | vol=dry | NDQ | 30min | std | 30 | 77% | +0.377 | 2.4 | +0.28 | +0.46 | +0.26 | +0.31 | +0.44 | +0.49 |
| smc_displacement | entry=top | XAUUSD | 15min | trend | 64 | 52% | +0.405 | 2.4 | +0.70 | +0.03 | +0.60 | +0.85 | -0.03 | +0.07 |
| rsi_pullback | default | XAUUSD | 15min | std | 79 | 63% | +0.255 | 2.4 | +0.26 | +0.25 | +0.35 | +0.12 | -0.20 | +0.75 |
| smc_displacement | default | XAUUSD | 15min | trend | 49 | 53% | +0.457 | 2.4 | +0.70 | +0.08 | +0.74 | +0.60 | -0.11 | +0.24 |
| trend_breakout | vol=impulse | US30 | 15min | std | 34 | 71% | +0.413 | 2.3 | +0.47 | +0.36 | +0.64 | +0.31 | +0.46 | +0.28 |
| smc_displacement | swing=3 | XAUUSD | 15min | std | 45 | 69% | +0.325 | 2.3 | +0.42 | +0.16 | +0.32 | +0.63 | +0.21 | +0.13 |
| ict_turtle_soup | level=session | US30 | 15min | trend | 62 | 48% | +0.438 | 2.3 | +0.48 | +0.38 | +0.42 | +0.55 | +0.68 | +0.04 |
| smc_displacement | default | XAUUSD | 15min | std | 49 | 67% | +0.299 | 2.2 | +0.47 | +0.03 | +0.31 | +0.84 | +0.03 | +0.04 |
| vwap | vol=dry | XAUUSD | 15min | trend | 81 | 46% | +0.335 | 2.1 | +0.28 | +0.39 | +0.18 | +0.37 | +0.50 | +0.30 |
| smc_ifvg | default | XAUUSD | 15min | std | 154 | 60% | +0.161 | 2.1 | +0.10 | +0.22 | -0.01 | +0.21 | +0.26 | +0.18 |
| sr_rejection | default | NDQ | 30min | trend | 117 | 48% | +0.265 | 2.1 | +0.19 | +0.35 | +0.26 | +0.11 | +0.19 | +0.48 |
| smc_displacement | stop=fvg_bot | XAUUSD | 15min | trend | 50 | 50% | +0.416 | 2.0 | +0.57 | +0.19 | +0.45 | +0.84 | +0.14 | +0.22 |
| smc_displacement | swing=3 | XAUUSD | 15min | trend | 45 | 51% | +0.397 | 2.0 | +0.53 | +0.15 | +0.66 | +0.24 | -0.14 | +0.32 |
| smc_displacement | disp_k=1.5 | XAUUSD | 15min | std | 30 | 70% | +0.326 | 2.0 | +0.46 | +0.17 | +0.23 | +1.15 | +0.21 | +0.14 |
| ict_turtle_soup | level=session | US30 | 15min | std | 62 | 58% | +0.342 | 2.0 | +0.44 | +0.21 | +0.40 | +0.48 | +0.60 | -0.24 |
| dtfx_zone | default | NDQ | 30min | std | 55 | 64% | +0.162 | 2.0 | +0.15 | +0.18 | +0.05 | +0.28 | +0.35 | -0.01 |
| smc_displacement | disp_k=1.0 | XAUUSD | 15min | trend | 67 | 49% | +0.314 | 2.0 | +0.47 | +0.05 | +0.69 | +0.11 | -0.11 | +0.26 |
| smc_choch | swing=2 | NDQ | 1h | trend | 38 | 61% | +0.237 | 1.9 | +0.24 | +0.23 | +0.27 | +0.22 | +0.27 | +0.18 |
| rsi_pullback | default | XAUUSD | 15min | trend | 77 | 48% | +0.291 | 1.9 | +0.38 | +0.19 | +0.41 | +0.33 | -0.33 | +0.74 |
| smc_bos_retest | tol_atr=0.3 | XAUUSD | 1h | trend | 45 | 62% | +0.191 | 1.9 | +0.34 | +0.02 | +0.30 | +0.40 | +0.04 | +0.01 |
| dtfx_zone | default | NDQ | 1h | std | 33 | 58% | +0.149 | 1.8 | +0.21 | +0.08 | +0.10 | +0.34 | +0.18 | -0.05 |
| smc_bos_retest | swing=2 | XAUUSD | 1h | trend | 44 | 61% | +0.208 | 1.8 | +0.25 | +0.14 | +0.20 | +0.35 | +0.37 | -0.12 |
| smc_displacement | stop=fvg_bot | XAUUSD | 15min | std | 50 | 62% | +0.275 | 1.8 | +0.36 | +0.15 | +0.25 | +0.61 | +0.09 | +0.19 |
| ict_turtle_soup | confirm=choch | NDQ | 15min | trend | 64 | 55% | +0.265 | 1.8 | +0.12 | +0.36 | +0.00 | +0.23 | +0.35 | +0.39 |
| smc_choch | swing=2 | NDQ | 1h | std | 38 | 61% | +0.148 | 1.8 | +0.22 | +0.05 | +0.15 | +0.29 | +0.04 | +0.06 |
| dtfx_wick_fib | level=50-70 | US30 | 1h | trend | 33 | 55% | +0.320 | 1.7 | +0.55 | +0.17 | +0.75 | +0.32 | +0.20 | +0.15 |
| vwap | tol_atr=0.3 | XAUUSD | 15min | trend | 209 | 41% | +0.163 | 1.7 | +0.08 | +0.26 | +0.10 | +0.06 | +0.36 | +0.15 |
| smc_displacement | disp_k=1.5 | XAUUSD | 15min | trend | 30 | 53% | +0.394 | 1.7 | +0.69 | +0.05 | +0.64 | +0.86 | -0.14 | +0.20 |
| trend_pullback | swing_bars=8 | NDQ | 15min | trend | 58 | 52% | +0.274 | 1.6 | +0.23 | +0.30 | -0.08 | +0.54 | +0.22 | +0.38 |
| london_breakout | min_body_atr=0.0 | EURUSD | 1h | trend | 40 | 65% | +0.200 | 1.6 | +0.03 | +0.37 | -0.22 | +0.35 | +0.31 | +0.43 |
| ict_amd | model=midnight | XAUUSD | 30min | std | 91 | 55% | +0.111 | 1.6 | +0.06 | +0.18 | -0.02 | +0.15 | +0.14 | +0.21 |
| smc_choch | swing=5 | XAUUSD | 15min | std | 88 | 52% | +0.117 | 1.6 | +0.08 | +0.15 | +0.08 | +0.09 | +0.31 | -0.02 |
| ict_turtle_soup | default | EURUSD | 1h | std | 40 | 62% | +0.165 | 1.6 | +0.17 | +0.15 | +0.37 | -0.04 | +0.23 | +0.08 |
| smc_bos_retest | tol_atr=0.15 | EURUSD | 1h | trend | 36 | 53% | +0.204 | 1.5 | +0.07 | +0.33 | -0.06 | +0.14 | +0.21 | +0.39 |
| macd_cross | default | NDQ | 15min | trend | 68 | 47% | +0.231 | 1.5 | +0.31 | +0.16 | +0.32 | +0.28 | +0.29 | +0.01 |
| vwap | vol=impulse | US30 | 15min | std | 55 | 53% | +0.261 | 1.5 | +0.34 | +0.21 | +0.48 | +0.23 | -0.14 | +0.43 |
| vwap | mode=reclaim | NDQ | 30min | trend | 110 | 47% | +0.181 | 1.5 | +0.27 | +0.11 | +0.36 | +0.11 | +0.34 | -0.15 |

167 cells qualify out of 2279 with ≥30 trades. With this many cells, a few will pass by luck alone — a t above ~3 is the bar for 'probably real'.

## 3 · Every setup, overall (default variant, all timeframes but 1m; std = 1R first target, trend = 2R first target, 15m+ only)

| setup | sym | exit | trades | win | avg R | first half | second half |
|---|---|---|---|---|---|---|---|
| dtfx_close_fib | AUDUSD | std | 77 | 22% | -0.416 | -0.49 | -0.36 |
| dtfx_close_fib | AUDUSD | trend | 77 | 19% | -0.483 | -0.57 | -0.41 |
| dtfx_close_fib | EURUSD | std | 62 | 47% | -0.033 | -0.09 | +0.02 |
| dtfx_close_fib | EURUSD | trend | 62 | 45% | -0.012 | +0.09 | -0.11 |
| dtfx_close_fib | GBPUSD | std | 55 | 38% | -0.238 | -0.34 | -0.16 |
| dtfx_close_fib | GBPUSD | trend | 55 | 29% | -0.186 | -0.35 | -0.05 |
| dtfx_close_fib | NDQ | std | 64 | 55% | -0.001 | -0.03 | +0.05 |
| dtfx_close_fib | NDQ | trend | 62 | 44% | -0.091 | -0.18 | +0.04 |
| dtfx_close_fib | US30 | std | 62 | 53% | +0.056 | +0.12 | -0.01 |
| dtfx_close_fib | US30 | trend | 61 | 44% | +0.048 | +0.15 | -0.05 |
| dtfx_close_fib | XAUUSD | std | 71 | 41% | -0.140 | -0.20 | -0.08 |
| dtfx_close_fib | XAUUSD | trend | 71 | 42% | -0.084 | -0.05 | -0.11 |
| dtfx_close_fib_brk | AUDUSD | std | 68 | 22% | -0.436 | -0.57 | -0.30 |
| dtfx_close_fib_brk | AUDUSD | trend | 68 | 21% | -0.513 | -0.64 | -0.39 |
| dtfx_close_fib_brk | EURUSD | std | 46 | 43% | -0.051 | -0.01 | -0.10 |
| dtfx_close_fib_brk | EURUSD | trend | 46 | 41% | +0.013 | +0.18 | -0.21 |
| dtfx_close_fib_brk | GBPUSD | std | 47 | 38% | -0.185 | -0.13 | -0.24 |
| dtfx_close_fib_brk | GBPUSD | trend | 47 | 36% | -0.129 | -0.04 | -0.22 |
| dtfx_close_fib_brk | NDQ | std | 40 | 60% | +0.155 | +0.15 | +0.16 |
| dtfx_close_fib_brk | NDQ | trend | 40 | 45% | +0.122 | +0.01 | +0.41 |
| dtfx_close_fib_brk | US30 | std | 51 | 51% | +0.027 | +0.16 | -0.13 |
| dtfx_close_fib_brk | US30 | trend | 51 | 45% | +0.079 | +0.37 | -0.25 |
| dtfx_close_fib_brk | XAUUSD | std | 57 | 46% | -0.129 | -0.18 | -0.06 |
| dtfx_close_fib_brk | XAUUSD | trend | 57 | 40% | -0.204 | -0.28 | -0.12 |
| dtfx_close_origin | AUDUSD | std | 67 | 39% | -0.250 | -0.28 | -0.23 |
| dtfx_close_origin | AUDUSD | trend | 66 | 35% | -0.277 | -0.44 | -0.13 |
| dtfx_close_origin | EURUSD | std | 62 | 47% | -0.115 | -0.19 | -0.05 |
| dtfx_close_origin | EURUSD | trend | 61 | 31% | -0.238 | -0.38 | -0.11 |
| dtfx_close_origin | GBPUSD | std | 53 | 49% | -0.058 | -0.16 | +0.02 |
| dtfx_close_origin | GBPUSD | trend | 53 | 36% | -0.012 | +0.02 | -0.03 |
| dtfx_close_origin | NDQ | std | 60 | 40% | -0.090 | -0.15 | -0.04 |
| dtfx_close_origin | NDQ | trend | 60 | 35% | -0.154 | -0.37 | +0.04 |
| dtfx_close_origin | US30 | std | 80 | 46% | -0.120 | -0.07 | -0.18 |
| dtfx_close_origin | US30 | trend | 80 | 44% | +0.060 | +0.14 | -0.03 |
| dtfx_close_origin | XAUUSD | std | 62 | 37% | -0.324 | -0.34 | -0.31 |
| dtfx_close_origin | XAUUSD | trend | 62 | 31% | -0.343 | -0.20 | -0.50 |
| dtfx_wick_fib | AUDUSD | std | 97 | 29% | -0.338 | -0.32 | -0.35 |
| dtfx_wick_fib | AUDUSD | trend | 96 | 26% | -0.341 | -0.39 | -0.31 |
| dtfx_wick_fib | EURUSD | std | 85 | 52% | +0.014 | +0.02 | -0.00 |
| dtfx_wick_fib | EURUSD | trend | 83 | 48% | +0.088 | +0.14 | +0.01 |
| dtfx_wick_fib | GBPUSD | std | 91 | 41% | -0.208 | -0.17 | -0.24 |
| dtfx_wick_fib | GBPUSD | trend | 91 | 29% | -0.225 | -0.19 | -0.26 |
| dtfx_wick_fib | NDQ | std | 104 | 56% | -0.043 | -0.15 | +0.09 |
| dtfx_wick_fib | NDQ | trend | 102 | 44% | -0.074 | -0.23 | +0.13 |
| dtfx_wick_fib | US30 | std | 77 | 52% | -0.053 | +0.04 | -0.13 |
| dtfx_wick_fib | US30 | trend | 75 | 37% | -0.159 | -0.01 | -0.28 |
| dtfx_wick_fib | XAUUSD | std | 114 | 47% | -0.034 | -0.03 | -0.04 |
| dtfx_wick_fib | XAUUSD | trend | 113 | 49% | +0.075 | +0.16 | -0.01 |
| dtfx_zone | AUDUSD | std | 255 | 38% | -0.156 | -0.14 | -0.17 |
| dtfx_zone | AUDUSD | trend | 247 | 34% | -0.215 | -0.22 | -0.21 |
| dtfx_zone | EURUSD | std | 242 | 38% | -0.218 | -0.28 | -0.14 |
| dtfx_zone | EURUSD | trend | 232 | 31% | -0.259 | -0.35 | -0.14 |
| dtfx_zone | GBPUSD | std | 231 | 44% | -0.088 | -0.09 | -0.08 |
| dtfx_zone | GBPUSD | trend | 222 | 36% | -0.089 | -0.10 | -0.08 |
| dtfx_zone | NDQ | std | 214 | 52% | +0.016 | +0.01 | +0.03 |
| dtfx_zone | NDQ | trend | 211 | 45% | -0.023 | -0.03 | -0.02 |
| dtfx_zone | US30 | std | 219 | 44% | -0.111 | -0.18 | -0.05 |
| dtfx_zone | US30 | trend | 214 | 37% | -0.036 | -0.07 | -0.01 |
| dtfx_zone | XAUUSD | std | 226 | 48% | -0.056 | -0.04 | -0.07 |
| dtfx_zone | XAUUSD | trend | 221 | 46% | -0.021 | +0.00 | -0.04 |
| ict_2022 | AUDUSD | std | 25 | 40% | -0.132 | -0.09 | -0.18 |
| ict_2022 | AUDUSD | trend | 25 | 24% | -0.270 | -0.24 | -0.30 |
| ict_2022 | EURUSD | std | 40 | 42% | -0.182 | -0.25 | -0.08 |
| ict_2022 | EURUSD | trend | 40 | 30% | -0.218 | -0.43 | +0.10 |
| ict_2022 | GBPUSD | std | 45 | 49% | +0.001 | -0.03 | +0.05 |
| ict_2022 | GBPUSD | trend | 45 | 36% | -0.090 | -0.16 | +0.01 |
| ict_2022 | NDQ | std | 30 | 53% | +0.047 | -0.03 | +0.10 |
| ict_2022 | NDQ | trend | 30 | 40% | -0.127 | -0.27 | -0.03 |
| ict_2022 | US30 | std | 34 | 56% | +0.057 | -0.18 | +0.26 |
| ict_2022 | US30 | trend | 34 | 41% | -0.054 | -0.22 | +0.10 |
| ict_2022 | XAUUSD | std | 25 | 56% | +0.147 | +0.15 | +0.14 |
| ict_2022 | XAUUSD | trend | 25 | 48% | +0.209 | +0.18 | +0.23 |
| ict_amd | AUDUSD | std | 80 | 42% | -0.010 | -0.09 | +0.11 |
| ict_amd | AUDUSD | trend | 80 | 41% | -0.003 | -0.12 | +0.16 |
| ict_amd | EURUSD | std | 140 | 47% | -0.051 | -0.01 | -0.11 |
| ict_amd | EURUSD | trend | 140 | 42% | -0.039 | -0.09 | +0.04 |
| ict_amd | GBPUSD | std | 140 | 46% | +0.044 | -0.00 | +0.12 |
| ict_amd | GBPUSD | trend | 140 | 42% | +0.080 | -0.02 | +0.24 |
| ict_amd | NDQ | std | 123 | 46% | -0.014 | -0.04 | +0.02 |
| ict_amd | NDQ | trend | 123 | 46% | +0.045 | -0.06 | +0.18 |
| ict_amd | US30 | std | 175 | 45% | -0.062 | +0.01 | -0.14 |
| ict_amd | US30 | trend | 175 | 29% | -0.237 | -0.12 | -0.36 |
| ict_amd | XAUUSD | std | 77 | 53% | +0.082 | +0.07 | +0.11 |
| ict_amd | XAUUSD | trend | 77 | 58% | +0.067 | +0.05 | +0.10 |
| ict_fvg_sweep | AUDUSD | std | 51 | 45% | +0.024 | +0.09 | -0.05 |
| ict_fvg_sweep | AUDUSD | trend | 51 | 41% | +0.009 | +0.18 | -0.18 |
| ict_fvg_sweep | EURUSD | std | 50 | 32% | -0.330 | -0.40 | -0.25 |
| ict_fvg_sweep | EURUSD | trend | 50 | 24% | -0.358 | -0.50 | -0.19 |
| ict_fvg_sweep | GBPUSD | std | 52 | 50% | -0.076 | -0.15 | +0.03 |
| ict_fvg_sweep | GBPUSD | trend | 52 | 35% | -0.172 | -0.24 | -0.08 |
| ict_fvg_sweep | NDQ | std | 38 | 39% | -0.359 | -0.66 | -0.20 |
| ict_fvg_sweep | NDQ | trend | 37 | 22% | -0.513 | -0.91 | -0.32 |
| ict_fvg_sweep | US30 | std | 49 | 57% | +0.195 | -0.18 | +0.65 |
| ict_fvg_sweep | US30 | trend | 48 | 40% | -0.034 | -0.39 | +0.43 |
| ict_fvg_sweep | XAUUSD | std | 36 | 56% | +0.226 | +0.27 | +0.17 |
| ict_fvg_sweep | XAUUSD | trend | 36 | 44% | +0.222 | +0.28 | +0.14 |
| ict_ote | AUDUSD | std | 241 | 41% | -0.161 | -0.13 | -0.19 |
| ict_ote | AUDUSD | trend | 235 | 32% | -0.254 | -0.21 | -0.30 |
| ict_ote | EURUSD | std | 228 | 37% | -0.280 | -0.30 | -0.26 |
| ict_ote | EURUSD | trend | 223 | 27% | -0.321 | -0.40 | -0.25 |
| ict_ote | GBPUSD | std | 244 | 44% | -0.087 | -0.14 | -0.03 |
| ict_ote | GBPUSD | trend | 238 | 34% | -0.104 | -0.08 | -0.12 |
| ict_ote | NDQ | std | 207 | 54% | -0.019 | -0.19 | +0.10 |
| ict_ote | NDQ | trend | 203 | 40% | -0.015 | -0.05 | +0.01 |
| ict_ote | US30 | std | 202 | 49% | -0.004 | +0.01 | -0.02 |
| ict_ote | US30 | trend | 200 | 42% | +0.116 | +0.01 | +0.20 |
| ict_ote | XAUUSD | std | 187 | 48% | -0.088 | -0.15 | -0.02 |
| ict_ote | XAUUSD | trend | 184 | 39% | -0.095 | -0.11 | -0.08 |
| ict_silver_bullet | AUDUSD | std | 13 | 38% | +0.014 | +0.57 | -0.64 |
| ict_silver_bullet | AUDUSD | trend | 13 | 38% | -0.018 | +0.52 | -0.65 |
| ict_silver_bullet | EURUSD | std | 7 | 71% | +0.370 | -0.34 | +0.66 |
| ict_silver_bullet | EURUSD | trend | 7 | 43% | +0.173 | -1.00 | +0.64 |
| ict_silver_bullet | GBPUSD | std | 9 | 44% | -0.189 | +0.30 | -0.80 |
| ict_silver_bullet | GBPUSD | trend | 9 | 33% | -0.124 | +0.36 | -0.73 |
| ict_silver_bullet | NDQ | std | 20 | 45% | +0.068 | +0.19 | -0.12 |
| ict_silver_bullet | NDQ | trend | 20 | 45% | +0.046 | +0.27 | -0.29 |
| ict_silver_bullet | US30 | std | 16 | 44% | -0.059 | -0.02 | -0.15 |
| ict_silver_bullet | US30 | trend | 16 | 44% | -0.005 | +0.15 | -0.34 |
| ict_silver_bullet | XAUUSD | std | 3 | 33% | -0.065 | -0.07 | — |
| ict_silver_bullet | XAUUSD | trend | 3 | 33% | +0.162 | +0.16 | — |
| ict_turtle_soup | AUDUSD | std | 340 | 40% | -0.196 | -0.08 | -0.31 |
| ict_turtle_soup | AUDUSD | trend | 340 | 33% | -0.172 | -0.12 | -0.22 |
| ict_turtle_soup | EURUSD | std | 354 | 44% | -0.128 | -0.16 | -0.08 |
| ict_turtle_soup | EURUSD | trend | 352 | 34% | -0.106 | -0.18 | -0.00 |
| ict_turtle_soup | GBPUSD | std | 387 | 42% | -0.117 | -0.03 | -0.23 |
| ict_turtle_soup | GBPUSD | trend | 386 | 31% | -0.146 | -0.07 | -0.26 |
| ict_turtle_soup | NDQ | std | 405 | 47% | -0.004 | +0.00 | -0.01 |
| ict_turtle_soup | NDQ | trend | 404 | 37% | +0.002 | +0.03 | -0.02 |
| ict_turtle_soup | US30 | std | 413 | 45% | -0.117 | -0.11 | -0.13 |
| ict_turtle_soup | US30 | trend | 413 | 34% | -0.109 | -0.12 | -0.09 |
| ict_turtle_soup | XAUUSD | std | 364 | 49% | -0.031 | -0.03 | -0.03 |
| ict_turtle_soup | XAUUSD | trend | 361 | 37% | -0.087 | -0.03 | -0.14 |
| london_breakout | AUDUSD | std | 101 | 45% | -0.115 | -0.32 | +0.04 |
| london_breakout | AUDUSD | trend | 101 | 48% | +0.073 | -0.32 | +0.36 |
| london_breakout | EURUSD | std | 155 | 47% | -0.033 | -0.09 | +0.02 |
| london_breakout | EURUSD | trend | 155 | 48% | +0.043 | -0.21 | +0.29 |
| london_breakout | GBPUSD | std | 166 | 45% | -0.021 | -0.10 | +0.09 |
| london_breakout | GBPUSD | trend | 166 | 37% | -0.063 | -0.28 | +0.24 |
| london_breakout | NDQ | std | 105 | 42% | -0.118 | -0.24 | +0.00 |
| london_breakout | NDQ | trend | 105 | 38% | -0.025 | -0.38 | +0.32 |
| london_breakout | US30 | std | 140 | 44% | -0.129 | -0.24 | -0.03 |
| london_breakout | US30 | trend | 140 | 27% | -0.237 | -0.38 | -0.12 |
| london_breakout | XAUUSD | std | 81 | 43% | -0.009 | -0.02 | -0.00 |
| london_breakout | XAUUSD | trend | 81 | 48% | +0.176 | -0.11 | +0.37 |
| macd_cross | AUDUSD | std | 113 | 45% | -0.079 | -0.09 | -0.06 |
| macd_cross | AUDUSD | trend | 110 | 46% | +0.030 | -0.08 | +0.14 |
| macd_cross | EURUSD | std | 127 | 51% | -0.033 | +0.01 | -0.08 |
| macd_cross | EURUSD | trend | 125 | 42% | +0.028 | +0.07 | -0.02 |
| macd_cross | GBPUSD | std | 123 | 45% | -0.055 | -0.07 | -0.04 |
| macd_cross | GBPUSD | trend | 122 | 38% | -0.037 | -0.07 | +0.01 |
| macd_cross | NDQ | std | 121 | 48% | -0.014 | +0.02 | -0.05 |
| macd_cross | NDQ | trend | 119 | 50% | +0.110 | +0.12 | +0.10 |
| macd_cross | US30 | std | 105 | 51% | -0.050 | -0.06 | -0.04 |
| macd_cross | US30 | trend | 104 | 41% | -0.086 | -0.26 | +0.14 |
| macd_cross | XAUUSD | std | 134 | 38% | -0.124 | -0.07 | -0.18 |
| macd_cross | XAUUSD | trend | 127 | 35% | -0.175 | -0.10 | -0.25 |
| rsi_pullback | AUDUSD | std | 112 | 54% | -0.033 | +0.10 | -0.13 |
| rsi_pullback | AUDUSD | trend | 111 | 44% | +0.077 | +0.41 | -0.15 |
| rsi_pullback | EURUSD | std | 122 | 43% | -0.093 | +0.08 | -0.23 |
| rsi_pullback | EURUSD | trend | 122 | 37% | -0.091 | +0.07 | -0.23 |
| rsi_pullback | GBPUSD | std | 119 | 34% | -0.332 | -0.37 | -0.30 |
| rsi_pullback | GBPUSD | trend | 119 | 29% | -0.243 | -0.27 | -0.22 |
| rsi_pullback | NDQ | std | 146 | 48% | -0.049 | +0.04 | -0.11 |
| rsi_pullback | NDQ | trend | 145 | 46% | +0.068 | +0.20 | -0.02 |
| rsi_pullback | US30 | std | 111 | 44% | -0.129 | -0.18 | -0.08 |
| rsi_pullback | US30 | trend | 111 | 32% | -0.133 | -0.18 | -0.08 |
| rsi_pullback | XAUUSD | std | 130 | 64% | +0.210 | +0.15 | +0.26 |
| rsi_pullback | XAUUSD | trend | 128 | 49% | +0.221 | +0.16 | +0.28 |
| smc_bos_retest | AUDUSD | std | 255 | 36% | -0.196 | -0.20 | -0.20 |
| smc_bos_retest | AUDUSD | trend | 244 | 31% | -0.239 | -0.25 | -0.23 |
| smc_bos_retest | EURUSD | std | 213 | 44% | -0.079 | -0.09 | -0.07 |
| smc_bos_retest | EURUSD | trend | 198 | 44% | +0.026 | -0.04 | +0.08 |
| smc_bos_retest | GBPUSD | std | 209 | 43% | -0.042 | +0.01 | -0.08 |
| smc_bos_retest | GBPUSD | trend | 198 | 39% | -0.069 | +0.04 | -0.15 |
| smc_bos_retest | NDQ | std | 245 | 47% | -0.026 | -0.11 | +0.04 |
| smc_bos_retest | NDQ | trend | 231 | 45% | +0.014 | -0.16 | +0.16 |
| smc_bos_retest | US30 | std | 232 | 44% | -0.142 | -0.19 | -0.10 |
| smc_bos_retest | US30 | trend | 217 | 36% | -0.170 | -0.13 | -0.20 |
| smc_bos_retest | XAUUSD | std | 264 | 51% | +0.023 | +0.07 | -0.03 |
| smc_bos_retest | XAUUSD | trend | 242 | 51% | +0.107 | +0.16 | +0.05 |
| smc_breaker | AUDUSD | std | 104 | 34% | -0.270 | -0.37 | -0.12 |
| smc_breaker | AUDUSD | trend | 104 | 23% | -0.360 | -0.52 | -0.12 |
| smc_breaker | EURUSD | std | 90 | 37% | -0.263 | -0.15 | -0.39 |
| smc_breaker | EURUSD | trend | 90 | 30% | -0.199 | -0.04 | -0.38 |
| smc_breaker | GBPUSD | std | 109 | 40% | -0.252 | -0.17 | -0.33 |
| smc_breaker | GBPUSD | trend | 109 | 28% | -0.238 | -0.14 | -0.34 |
| smc_breaker | NDQ | std | 89 | 45% | -0.133 | -0.27 | +0.02 |
| smc_breaker | NDQ | trend | 88 | 38% | -0.045 | -0.06 | -0.02 |
| smc_breaker | US30 | std | 98 | 47% | -0.085 | -0.20 | +0.03 |
| smc_breaker | US30 | trend | 98 | 38% | -0.079 | -0.32 | +0.16 |
| smc_breaker | XAUUSD | std | 99 | 49% | +0.033 | -0.10 | +0.12 |
| smc_breaker | XAUUSD | trend | 99 | 41% | -0.000 | -0.18 | +0.11 |
| smc_choch | AUDUSD | std | 233 | 39% | -0.177 | -0.15 | -0.20 |
| smc_choch | AUDUSD | trend | 231 | 35% | -0.161 | -0.23 | -0.10 |
| smc_choch | EURUSD | std | 208 | 44% | -0.089 | -0.19 | -0.01 |
| smc_choch | EURUSD | trend | 206 | 42% | -0.081 | -0.21 | +0.03 |
| smc_choch | GBPUSD | std | 235 | 42% | -0.130 | -0.06 | -0.21 |
| smc_choch | GBPUSD | trend | 235 | 35% | -0.074 | -0.08 | -0.07 |
| smc_choch | NDQ | std | 191 | 50% | -0.023 | -0.04 | -0.00 |
| smc_choch | NDQ | trend | 191 | 47% | +0.008 | -0.09 | +0.09 |
| smc_choch | US30 | std | 206 | 46% | -0.083 | -0.11 | -0.06 |
| smc_choch | US30 | trend | 205 | 36% | -0.090 | -0.15 | -0.04 |
| smc_choch | XAUUSD | std | 216 | 48% | -0.010 | +0.03 | -0.05 |
| smc_choch | XAUUSD | trend | 212 | 40% | -0.076 | -0.05 | -0.09 |
| smc_displacement | AUDUSD | std | 106 | 34% | -0.315 | -0.26 | -0.37 |
| smc_displacement | AUDUSD | trend | 106 | 25% | -0.366 | -0.39 | -0.34 |
| smc_displacement | EURUSD | std | 101 | 39% | -0.251 | -0.34 | -0.16 |
| smc_displacement | EURUSD | trend | 101 | 26% | -0.271 | -0.34 | -0.19 |
| smc_displacement | GBPUSD | std | 99 | 39% | -0.183 | -0.16 | -0.20 |
| smc_displacement | GBPUSD | trend | 96 | 33% | -0.104 | -0.10 | -0.10 |
| smc_displacement | NDQ | std | 66 | 50% | -0.011 | -0.08 | +0.06 |
| smc_displacement | NDQ | trend | 65 | 38% | -0.071 | -0.36 | +0.23 |
| smc_displacement | US30 | std | 68 | 53% | -0.003 | +0.02 | -0.03 |
| smc_displacement | US30 | trend | 67 | 34% | -0.186 | -0.21 | -0.16 |
| smc_displacement | XAUUSD | std | 80 | 60% | +0.132 | +0.32 | -0.07 |
| smc_displacement | XAUUSD | trend | 80 | 51% | +0.247 | +0.48 | -0.01 |
| smc_ifvg | AUDUSD | std | 299 | 34% | -0.365 | -0.26 | -0.46 |
| smc_ifvg | AUDUSD | trend | 294 | 25% | -0.360 | -0.30 | -0.42 |
| smc_ifvg | EURUSD | std | 310 | 44% | -0.138 | -0.16 | -0.11 |
| smc_ifvg | EURUSD | trend | 304 | 34% | -0.069 | -0.11 | -0.03 |
| smc_ifvg | GBPUSD | std | 260 | 37% | -0.280 | -0.27 | -0.29 |
| smc_ifvg | GBPUSD | trend | 258 | 29% | -0.226 | -0.23 | -0.22 |
| smc_ifvg | NDQ | std | 240 | 48% | -0.078 | -0.18 | +0.00 |
| smc_ifvg | NDQ | trend | 238 | 36% | -0.054 | -0.13 | +0.01 |
| smc_ifvg | US30 | std | 234 | 47% | -0.083 | -0.05 | -0.12 |
| smc_ifvg | US30 | trend | 232 | 34% | -0.059 | -0.07 | -0.05 |
| smc_ifvg | XAUUSD | std | 276 | 57% | +0.110 | +0.09 | +0.13 |
| smc_ifvg | XAUUSD | trend | 270 | 42% | +0.099 | +0.06 | +0.14 |
| smc_liquidity_sweep | AUDUSD | std | 95 | 39% | -0.159 | -0.19 | -0.12 |
| smc_liquidity_sweep | AUDUSD | trend | 95 | 39% | -0.142 | -0.25 | -0.03 |
| smc_liquidity_sweep | EURUSD | std | 130 | 47% | -0.032 | +0.05 | -0.17 |
| smc_liquidity_sweep | EURUSD | trend | 130 | 40% | -0.027 | -0.05 | +0.02 |
| smc_liquidity_sweep | GBPUSD | std | 133 | 46% | -0.044 | +0.04 | -0.18 |
| smc_liquidity_sweep | GBPUSD | trend | 133 | 37% | -0.026 | -0.02 | -0.04 |
| smc_liquidity_sweep | NDQ | std | 105 | 49% | +0.027 | +0.09 | -0.05 |
| smc_liquidity_sweep | NDQ | trend | 105 | 50% | +0.177 | +0.26 | +0.09 |
| smc_liquidity_sweep | US30 | std | 129 | 50% | +0.053 | +0.12 | -0.02 |
| smc_liquidity_sweep | US30 | trend | 129 | 33% | -0.099 | +0.03 | -0.23 |
| smc_liquidity_sweep | XAUUSD | std | 76 | 57% | +0.028 | -0.14 | +0.20 |
| smc_liquidity_sweep | XAUUSD | trend | 76 | 50% | +0.022 | -0.12 | +0.17 |
| smc_mss | AUDUSD | std | 80 | 36% | -0.113 | -0.20 | -0.05 |
| smc_mss | AUDUSD | trend | 78 | 41% | -0.005 | -0.09 | +0.06 |
| smc_mss | EURUSD | std | 86 | 52% | -0.006 | -0.16 | +0.19 |
| smc_mss | EURUSD | trend | 86 | 47% | -0.007 | -0.24 | +0.28 |
| smc_mss | GBPUSD | std | 113 | 40% | -0.054 | -0.03 | -0.07 |
| smc_mss | GBPUSD | trend | 111 | 36% | -0.035 | -0.12 | +0.05 |
| smc_mss | NDQ | std | 84 | 45% | -0.053 | -0.02 | -0.08 |
| smc_mss | NDQ | trend | 84 | 44% | +0.047 | +0.15 | -0.02 |
| smc_mss | US30 | std | 87 | 51% | +0.048 | -0.13 | +0.21 |
| smc_mss | US30 | trend | 87 | 38% | -0.089 | -0.32 | +0.13 |
| smc_mss | XAUUSD | std | 77 | 52% | +0.021 | +0.09 | -0.06 |
| smc_mss | XAUUSD | trend | 77 | 51% | +0.016 | +0.02 | +0.01 |
| smc_order_block | AUDUSD | std | 191 | 35% | -0.358 | -0.31 | -0.40 |
| smc_order_block | AUDUSD | trend | 188 | 23% | -0.379 | -0.42 | -0.34 |
| smc_order_block | EURUSD | std | 179 | 41% | -0.171 | -0.21 | -0.13 |
| smc_order_block | EURUSD | trend | 177 | 33% | -0.128 | -0.29 | +0.07 |
| smc_order_block | GBPUSD | std | 187 | 38% | -0.303 | -0.29 | -0.31 |
| smc_order_block | GBPUSD | trend | 187 | 30% | -0.193 | -0.13 | -0.24 |
| smc_order_block | NDQ | std | 175 | 50% | -0.066 | -0.18 | +0.01 |
| smc_order_block | NDQ | trend | 174 | 34% | -0.100 | -0.24 | -0.01 |
| smc_order_block | US30 | std | 157 | 47% | -0.058 | -0.11 | -0.00 |
| smc_order_block | US30 | trend | 157 | 34% | -0.041 | -0.20 | +0.12 |
| smc_order_block | XAUUSD | std | 176 | 41% | -0.188 | -0.21 | -0.17 |
| smc_order_block | XAUUSD | trend | 175 | 31% | -0.174 | -0.23 | -0.12 |
| smt_divergence | NDQ | std | 88 | 52% | +0.082 | +0.22 | -0.02 |
| smt_divergence | NDQ | trend | 88 | 44% | +0.126 | +0.31 | -0.02 |
| smt_divergence | US30 | std | 107 | 46% | -0.144 | -0.03 | -0.25 |
| smt_divergence | US30 | trend | 106 | 28% | -0.308 | -0.26 | -0.35 |
| sr_rejection | AUDUSD | std | 528 | 39% | -0.258 | -0.25 | -0.26 |
| sr_rejection | AUDUSD | trend | 497 | 29% | -0.261 | -0.27 | -0.25 |
| sr_rejection | EURUSD | std | 485 | 41% | -0.214 | -0.15 | -0.27 |
| sr_rejection | EURUSD | trend | 474 | 31% | -0.163 | -0.13 | -0.19 |
| sr_rejection | GBPUSD | std | 494 | 35% | -0.322 | -0.33 | -0.32 |
| sr_rejection | GBPUSD | trend | 490 | 26% | -0.296 | -0.29 | -0.30 |
| sr_rejection | NDQ | std | 453 | 48% | -0.023 | -0.08 | +0.03 |
| sr_rejection | NDQ | trend | 440 | 35% | -0.059 | -0.09 | -0.03 |
| sr_rejection | US30 | std | 433 | 44% | -0.074 | -0.06 | -0.09 |
| sr_rejection | US30 | trend | 421 | 36% | -0.017 | -0.09 | +0.05 |
| sr_rejection | XAUUSD | std | 580 | 48% | -0.043 | -0.01 | -0.08 |
| sr_rejection | XAUUSD | trend | 563 | 35% | -0.082 | -0.00 | -0.17 |
| stoic_sbs | AUDUSD | std | 20 | 45% | -0.043 | -0.00 | -0.09 |
| stoic_sbs | AUDUSD | trend | 20 | 45% | +0.193 | +0.20 | +0.18 |
| stoic_sbs | EURUSD | std | 15 | 47% | -0.284 | -0.10 | -0.37 |
| stoic_sbs | EURUSD | trend | 15 | 33% | -0.251 | -0.72 | -0.02 |
| stoic_sbs | GBPUSD | std | 17 | 53% | -0.011 | +0.17 | -0.17 |
| stoic_sbs | GBPUSD | trend | 17 | 35% | -0.178 | -0.13 | -0.22 |
| stoic_sbs | NDQ | std | 10 | 30% | -0.569 | -0.83 | -0.31 |
| stoic_sbs | NDQ | trend | 10 | 20% | -0.770 | -1.00 | -0.54 |
| stoic_sbs | US30 | std | 7 | 29% | -0.375 | -0.61 | -0.07 |
| stoic_sbs | US30 | trend | 7 | 14% | -0.593 | -1.00 | -0.05 |
| stoic_sbs | XAUUSD | std | 9 | 78% | +0.123 | +0.40 | -0.09 |
| stoic_sbs | XAUUSD | trend | 9 | 67% | +0.009 | +0.20 | -0.15 |
| trend_breakout | AUDUSD | std | 337 | 36% | -0.244 | -0.28 | -0.21 |
| trend_breakout | AUDUSD | trend | 333 | 29% | -0.220 | -0.35 | -0.10 |
| trend_breakout | EURUSD | std | 261 | 38% | -0.156 | -0.17 | -0.14 |
| trend_breakout | EURUSD | trend | 261 | 30% | -0.154 | -0.21 | -0.11 |
| trend_breakout | GBPUSD | std | 282 | 39% | -0.184 | -0.10 | -0.28 |
| trend_breakout | GBPUSD | trend | 281 | 30% | -0.168 | -0.07 | -0.27 |
| trend_breakout | NDQ | std | 279 | 51% | +0.011 | -0.00 | +0.02 |
| trend_breakout | NDQ | trend | 274 | 42% | +0.044 | -0.00 | +0.08 |
| trend_breakout | US30 | std | 235 | 50% | -0.024 | -0.02 | -0.03 |
| trend_breakout | US30 | trend | 231 | 37% | -0.029 | +0.04 | -0.10 |
| trend_breakout | XAUUSD | std | 255 | 53% | +0.080 | +0.14 | +0.03 |
| trend_breakout | XAUUSD | trend | 254 | 43% | +0.095 | +0.13 | +0.06 |
| trend_pullback | AUDUSD | std | 129 | 44% | -0.177 | -0.26 | -0.07 |
| trend_pullback | AUDUSD | trend | 125 | 30% | -0.252 | -0.31 | -0.18 |
| trend_pullback | EURUSD | std | 127 | 37% | -0.227 | -0.13 | -0.31 |
| trend_pullback | EURUSD | trend | 123 | 28% | -0.255 | -0.24 | -0.27 |
| trend_pullback | GBPUSD | std | 152 | 46% | -0.089 | -0.07 | -0.11 |
| trend_pullback | GBPUSD | trend | 147 | 33% | -0.154 | -0.13 | -0.18 |
| trend_pullback | NDQ | std | 133 | 59% | +0.093 | -0.12 | +0.23 |
| trend_pullback | NDQ | trend | 129 | 49% | +0.162 | -0.08 | +0.33 |
| trend_pullback | US30 | std | 128 | 42% | -0.141 | -0.25 | -0.02 |
| trend_pullback | US30 | trend | 124 | 35% | -0.050 | -0.19 | +0.10 |
| trend_pullback | XAUUSD | std | 104 | 45% | -0.094 | +0.06 | -0.30 |
| trend_pullback | XAUUSD | trend | 103 | 41% | -0.099 | +0.20 | -0.50 |
| vwap | AUDUSD | std | 372 | 39% | -0.225 | -0.17 | -0.28 |
| vwap | AUDUSD | trend | 341 | 30% | -0.252 | -0.24 | -0.26 |
| vwap | EURUSD | std | 382 | 42% | -0.208 | -0.22 | -0.20 |
| vwap | EURUSD | trend | 369 | 29% | -0.228 | -0.32 | -0.14 |
| vwap | GBPUSD | std | 346 | 38% | -0.267 | -0.21 | -0.32 |
| vwap | GBPUSD | trend | 336 | 27% | -0.285 | -0.24 | -0.33 |
| vwap | NDQ | std | 301 | 50% | -0.007 | -0.14 | +0.08 |
| vwap | NDQ | trend | 287 | 39% | -0.002 | -0.26 | +0.18 |
| vwap | US30 | std | 375 | 46% | -0.030 | -0.09 | +0.01 |
| vwap | US30 | trend | 366 | 33% | -0.102 | -0.19 | -0.03 |
| vwap | XAUUSD | std | 322 | 53% | +0.079 | +0.05 | +0.12 |
| vwap | XAUUSD | trend | 304 | 39% | +0.084 | +0.01 | +0.18 |
| zone_confluence | AUDUSD | std | 144 | 41% | -0.175 | -0.19 | -0.16 |
| zone_confluence | AUDUSD | trend | 142 | 28% | -0.314 | -0.30 | -0.33 |
| zone_confluence | EURUSD | std | 170 | 44% | -0.169 | -0.24 | -0.09 |
| zone_confluence | EURUSD | trend | 165 | 32% | -0.193 | -0.36 | -0.00 |
| zone_confluence | GBPUSD | std | 164 | 44% | -0.157 | -0.16 | -0.15 |
| zone_confluence | GBPUSD | trend | 161 | 34% | -0.172 | -0.13 | -0.21 |
| zone_confluence | NDQ | std | 151 | 50% | -0.112 | -0.20 | -0.04 |
| zone_confluence | NDQ | trend | 148 | 33% | -0.210 | -0.19 | -0.22 |
| zone_confluence | US30 | std | 148 | 45% | -0.002 | -0.11 | +0.12 |
| zone_confluence | US30 | trend | 145 | 42% | +0.043 | -0.10 | +0.21 |
| zone_confluence | XAUUSD | std | 133 | 50% | -0.023 | -0.04 | -0.01 |
| zone_confluence | XAUUSD | trend | 130 | 38% | -0.133 | -0.10 | -0.16 |

## 4 · Best cell per setup (≥30 trades, by t-stat)

| setup | variant | sym | tf | exit | trades | win | avg R | t | quarters positive |
|---|---|---|---|---|---|---|---|---|---|
| smc_displacement | disp_k=1.0 | XAUUSD | 15min | std | 67 | 66% | +0.279 | 2.5 | 4/4 |
| vwap | vol=dry | XAUUSD | 15min | std | 84 | 61% | +0.319 | 2.5 | 4/4 |
| trend_breakout | vol=impulse | US30 | 15min | trend | 33 | 58% | +0.654 | 2.5 | 4/4 |
| rsi_pullback | default | XAUUSD | 15min | std | 79 | 63% | +0.255 | 2.4 | 3/4 |
| ict_turtle_soup | level=session | US30 | 15min | trend | 62 | 48% | +0.438 | 2.3 | 4/4 |
| smc_ifvg | default | XAUUSD | 15min | std | 154 | 60% | +0.161 | 2.1 | 3/4 |
| sr_rejection | default | NDQ | 30min | trend | 117 | 48% | +0.265 | 2.1 | 4/4 |
| dtfx_zone | default | NDQ | 30min | std | 55 | 64% | +0.162 | 2.0 | 3/4 |
| smc_choch | swing=2 | NDQ | 1h | trend | 38 | 61% | +0.237 | 1.9 | 4/4 |
| smc_bos_retest | tol_atr=0.3 | XAUUSD | 1h | trend | 45 | 62% | +0.191 | 1.9 | 4/4 |
| dtfx_wick_fib | level=50-70 | NDQ | 1h | trend | 36 | 67% | +0.264 | 1.9 | 3/4 |
| dtfx_close_fib | level=0.3 | XAUUSD | 1h | std | 30 | 73% | +0.109 | 1.6 | 3/4 |
| trend_pullback | swing_bars=8 | NDQ | 15min | trend | 58 | 52% | +0.274 | 1.6 | 3/4 |
| ict_amd | model=midnight | XAUUSD | 30min | trend | 91 | 52% | +0.176 | 1.6 | 2/4 |
| london_breakout | min_body_atr=0.0 | EURUSD | 1h | trend | 40 | 65% | +0.200 | 1.6 | 3/4 |
| macd_cross | default | NDQ | 15min | trend | 68 | 47% | +0.231 | 1.5 | 4/4 |
| smc_liquidity_sweep | default | NDQ | 30min | trend | 33 | 55% | +0.283 | 1.5 | 3/4 |
| dtfx_close_fib_brk | level=0.3 | NDQ | 15min | trend | 45 | 49% | +0.251 | 1.4 | 3/4 |
| ict_ote | default | US30 | 30min | trend | 58 | 45% | +0.250 | 1.3 | 2/4 |
| smt_divergence | confirm=reclaim | US30 | 1h | std | 39 | 59% | +0.232 | 1.3 | 4/4 |
| dtfx_close_origin | confirm=touch | XAUUSD | 1h | trend | 52 | 50% | +0.192 | 1.2 | 3/4 |
| smc_mss | sweep_bars=10 | XAUUSD | 15min | std | 34 | 62% | +0.145 | 1.2 | 3/4 |
| smc_order_block | default | US30 | 30min | trend | 45 | 47% | +0.215 | 1.0 | 3/4 |
| zone_confluence | within=4 | US30 | 30min | trend | 45 | 44% | +0.164 | 0.8 | 2/4 |
| ict_2022 | discount=False | US30 | 15min | std | 48 | 60% | +0.095 | 0.7 | 2/4 |
| smc_breaker | default | US30 | 15min | trend | 61 | 39% | +0.033 | 0.2 | 2/4 |
| ict_silver_bullet | require_sweep=False | AUDUSD | 15min | std | 34 | 35% | -0.123 | -0.6 | 1/4 |
