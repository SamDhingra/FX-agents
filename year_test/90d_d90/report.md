# Strategy test — 90 days · costs oanda · d90

Created 2026-10-07 20:17 NY · trades 2026-07-09 → 2026-10-07 · 1,013,423 simulated trades · 24,120 cells

R is per trade in units of its own risk, after spread. Quarters split the period in four equal parts; an edge worth trading is positive in most quarters, not just on average. 1-minute cells are listed but the playbook doesn't trade 1m (spread is too large a share of the bar).

## 1 · The playbook system, replayed week by week on unseen data

Each week: pick cells from the trailing 60 days, trade them the next week, capacity rules on. This is the number that says whether the approach works.

- trades **282**, win rate **45%**, avg **-0.058R**, total **-16.33R**, profit factor 0.8, worst drawdown -22.24R, t-stat -1.59, chance it's really ≤0: 0.938
- without the 3 best trades: -21.17R
- XAUUSD: 186 trades, 46% win, -3.29R
- NDQ: 59 trades, 36% win, -12.38R
- US30: 20 trades, 70% win, +1.65R
- EURUSD: 12 trades, 42% win, -2.54R
- GBPUSD: 5 trades, 60% win, +0.24R

By month (R): 2026-08 -31.5 (125) · 2026-09 +6.8 (133) · 2026-10 +3.4 (24)

Positive weeks: 3 of 10

## 2 · Cells that held up (≥30 trades, positive in both halves and ≥3 of 4 quarters)

| setup | variant | sym | tf | exit | trades | win | avg R | t | H1 | H2 | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| smc_mss | default | XAUUSD | 3min | tp1.5 | 39 | 64% | +0.547 | 2.8 | +0.55 | +0.55 | +0.56 | +0.54 | +0.94 | +0.24 |
| smc_mss | default | XAUUSD | 3min | tp2 | 39 | 59% | +0.603 | 2.8 | +0.71 | +0.44 | +0.69 | +0.73 | +0.86 | +0.12 |
| dtfx_wick_fib | level=50-70 | NDQ | 15min | std | 41 | 71% | +0.357 | 2.4 | +0.42 | +0.28 | +0.32 | +0.54 | +0.31 | +0.23 |
| smc_ifvg | default | XAUUSD | 15min | tp1 | 42 | 67% | +0.335 | 2.3 | +0.20 | +0.41 | +0.26 | +0.16 | +0.73 | +0.11 |
| dtfx_close_fib | sessions=killzones | US30 | 1min | std | 53 | 62% | +0.504 | 2.2 | +0.21 | +0.71 | +0.30 | -0.01 | +0.21 | +1.18 |
| dtfx_wick_fib | level=50-70 | NDQ | 15min | tp1 | 41 | 71% | +0.259 | 2.1 | +0.35 | +0.15 | +0.21 | +0.53 | +0.21 | +0.06 |
| smc_mss | sweep_bars=10 | XAUUSD | 3min | tp2 | 30 | 53% | +0.560 | 2.1 | +0.77 | +0.20 | +0.87 | +0.68 | +0.91 | -0.39 |
| smc_displacement | default | US30 | 5min | std | 31 | 61% | +0.733 | 2.1 | +0.54 | +0.89 | +0.51 | +0.56 | +1.79 | +0.40 |
| dtfx_wick_fib | level=50-70 | NDQ | 15min | trend | 39 | 56% | +0.403 | 2.1 | +0.70 | +0.06 | +0.83 | +0.55 | -0.06 | +0.24 |
| ict_turtle_soup | confirm=choch | XAUUSD | 3min | tp1.5 | 47 | 60% | +0.347 | 2.1 | +0.43 | +0.26 | +0.61 | +0.30 | +0.36 | +0.09 |
| dtfx_wick_fib | level=50-70 | NDQ | 15min | tp2 | 41 | 66% | +0.333 | 2.1 | +0.52 | +0.12 | +0.41 | +0.65 | +0.11 | +0.13 |
| dtfx_wick_fib | default | US30 | 1min | std | 127 | 59% | +0.242 | 2.0 | +0.04 | +0.38 | -0.06 | +0.19 | +0.18 | +0.57 |
| smc_mss | swing=3 | XAUUSD | 1min | tp2 | 93 | 47% | +0.296 | 2.0 | +0.26 | +0.32 | -0.15 | +0.58 | +0.50 | +0.10 |
| dtfx_wick_fib | default | US30 | 1min | tp2 | 131 | 42% | +0.259 | 2.0 | +0.12 | +0.35 | +0.03 | +0.27 | +0.34 | +0.36 |
| smc_mss | sweep_bars=10 | XAUUSD | 3min | tp1.5 | 30 | 57% | +0.471 | 2.0 | +0.59 | +0.26 | +0.73 | +0.47 | +0.70 | -0.11 |
| dtfx_close_fib | default | US30 | 1min | std | 86 | 58% | +0.312 | 1.9 | +0.02 | +0.48 | +0.06 | -0.06 | +0.23 | +0.81 |
| dtfx_wick_fib | sessions=killzones | US30 | 1min | std | 79 | 59% | +0.325 | 1.9 | +0.02 | +0.57 | +0.06 | -0.07 | +0.20 | +0.88 |
| smc_mss | swing=3 | XAUUSD | 1min | tp1.5 | 94 | 51% | +0.239 | 1.9 | +0.17 | +0.30 | -0.32 | +0.53 | +0.38 | +0.19 |
| ict_turtle_soup | confirm=choch | XAUUSD | 3min | tp1 | 48 | 65% | +0.239 | 1.9 | +0.29 | +0.18 | +0.39 | +0.23 | +0.22 | +0.10 |
| smc_mss | default | XAUUSD | 3min | tp1 | 39 | 67% | +0.269 | 1.9 | +0.16 | +0.43 | +0.16 | +0.16 | +0.63 | +0.27 |
| smc_displacement | default | US30 | 5min | tp1 | 31 | 65% | +0.325 | 1.8 | +0.04 | +0.56 | -0.03 | +0.10 | +0.85 | +0.40 |
| smc_mss | sweep_bars=10 | XAUUSD | 1min | tp2 | 108 | 43% | +0.263 | 1.8 | +0.31 | +0.22 | +0.19 | +0.42 | +0.35 | +0.01 |
| smc_displacement | default | US30 | 5min | tp1.5 | 31 | 55% | +0.423 | 1.8 | +0.10 | +0.69 | -0.08 | +0.23 | +1.22 | +0.40 |
| smc_mss | default | XAUUSD | 3min | std | 39 | 67% | +0.268 | 1.8 | +0.14 | +0.46 | +0.04 | +0.21 | +0.85 | +0.15 |
| dtfx_wick_fib | level=50-70 | NDQ | 15min | tp1.5 | 41 | 66% | +0.258 | 1.8 | +0.45 | +0.03 | +0.33 | +0.60 | +0.03 | +0.04 |
| smc_mss | disp_k=0.8 | XAUUSD | 3min | tp2 | 52 | 50% | +0.333 | 1.8 | +0.54 | +0.09 | +0.56 | +0.52 | +0.31 | -0.06 |
| ict_turtle_soup | confirm=choch | XAUUSD | 3min | std | 48 | 65% | +0.232 | 1.8 | +0.20 | +0.27 | +0.30 | +0.13 | +0.32 | +0.18 |
| dtfx_wick_fib | vol=impulse | US30 | 1min | std | 44 | 61% | +0.343 | 1.7 | +0.00 | +0.49 | +0.15 | -0.32 | +0.24 | +0.71 |
| dtfx_close_fib | sessions=killzones | US30 | 1min | tp1 | 59 | 59% | +0.236 | 1.7 | +0.22 | +0.25 | +0.26 | +0.09 | +0.13 | +0.37 |
| dtfx_close_fib | sessions=killzones | US30 | 1min | scalp | 59 | 58% | +0.222 | 1.7 | +0.21 | +0.23 | +0.25 | +0.09 | +0.17 | +0.29 |
| dtfx_wick_fib | sessions=killzones | US30 | 1min | tp2 | 81 | 43% | +0.282 | 1.7 | +0.13 | +0.41 | +0.06 | +0.26 | +0.27 | +0.51 |
| ict_amd | model=midnight | US30 | 15min | std | 34 | 62% | +0.355 | 1.7 | +0.21 | +0.50 | +0.12 | +0.39 | +0.76 | +0.26 |
| ict_amd | model=midnight | US30 | 5min | tp2 | 38 | 55% | +0.372 | 1.7 | +0.40 | +0.34 | +0.46 | +0.32 | +0.37 | +0.31 |
| ict_turtle_soup | confirm=choch | XAUUSD | 3min | scalp | 50 | 66% | +0.142 | 1.7 | +0.13 | +0.15 | +0.10 | +0.16 | +0.02 | +0.40 |
| dtfx_close_fib | default | US30 | 1min | tp2 | 90 | 42% | +0.265 | 1.7 | +0.08 | +0.38 | +0.19 | -0.16 | +0.40 | +0.36 |
| ict_amd | model=midnight | US30 | 15min | tp1 | 34 | 62% | +0.261 | 1.7 | +0.30 | +0.22 | +0.25 | +0.40 | +0.10 | +0.33 |
| vwap | mode=reclaim | XAUUSD | 5min | scalp | 118 | 53% | +0.125 | 1.7 | +0.03 | +0.20 | +0.01 | +0.05 | +0.15 | +0.23 |
| ict_amd | model=midnight | US30 | 3min | tp2 | 37 | 57% | +0.361 | 1.7 | +0.16 | +0.57 | +0.46 | -0.35 | +0.71 | +0.43 |
| ict_amd | model=midnight | US30 | 1min | tp2 | 37 | 51% | +0.394 | 1.7 | +0.18 | +0.62 | +0.51 | -0.53 | +0.87 | +0.42 |
| smc_choch | vol=impulse | XAUUSD | 1min | tp1.5 | 109 | 49% | +0.196 | 1.7 | +0.02 | +0.35 | +0.04 | +0.01 | +0.52 | +0.14 |

304 cells qualify out of 7571 with ≥30 trades. With this many cells, a few will pass by luck alone — a t above ~3 is the bar for 'probably real'.

## 3 · Every setup, overall (default variant, all timeframes but 1m; std = 1R first target, trend = 2R first target, 15m+ only)

| setup | sym | exit | trades | win | avg R | first half | second half |
|---|---|---|---|---|---|---|---|
| dtfx_close_fib | AUDUSD | std | 78 | 27% | -0.425 | -0.41 | -0.44 |
| dtfx_close_fib | AUDUSD | trend | 26 | 19% | -0.502 | -0.43 | -0.59 |
| dtfx_close_fib | EURUSD | std | 64 | 48% | +0.008 | -0.09 | +0.14 |
| dtfx_close_fib | EURUSD | trend | 16 | 31% | -0.090 | -0.04 | -0.21 |
| dtfx_close_fib | GBPUSD | std | 52 | 42% | -0.202 | -0.45 | +0.09 |
| dtfx_close_fib | GBPUSD | trend | 16 | 31% | -0.028 | -0.17 | +0.21 |
| dtfx_close_fib | NDQ | std | 66 | 53% | -0.042 | -0.09 | +0.02 |
| dtfx_close_fib | NDQ | trend | 13 | 38% | -0.106 | -0.19 | +0.03 |
| dtfx_close_fib | US30 | std | 79 | 42% | -0.079 | -0.29 | +0.18 |
| dtfx_close_fib | US30 | trend | 16 | 38% | -0.139 | +0.06 | -0.47 |
| dtfx_close_fib | XAUUSD | std | 74 | 54% | +0.067 | +0.05 | +0.09 |
| dtfx_close_fib | XAUUSD | trend | 17 | 35% | -0.270 | -0.34 | -0.16 |
| dtfx_close_fib_brk | AUDUSD | std | 64 | 31% | -0.399 | -0.37 | -0.44 |
| dtfx_close_fib_brk | AUDUSD | trend | 22 | 23% | -0.555 | -0.57 | -0.53 |
| dtfx_close_fib_brk | EURUSD | std | 54 | 37% | -0.260 | -0.38 | -0.10 |
| dtfx_close_fib_brk | EURUSD | trend | 10 | 40% | -0.157 | -0.52 | +0.20 |
| dtfx_close_fib_brk | GBPUSD | std | 50 | 28% | -0.426 | -0.62 | -0.11 |
| dtfx_close_fib_brk | GBPUSD | trend | 11 | 27% | -0.091 | -0.12 | -0.01 |
| dtfx_close_fib_brk | NDQ | std | 46 | 57% | +0.014 | -0.05 | +0.09 |
| dtfx_close_fib_brk | NDQ | trend | 8 | 62% | +0.464 | +0.64 | +0.16 |
| dtfx_close_fib_brk | US30 | std | 53 | 32% | -0.247 | -0.44 | -0.05 |
| dtfx_close_fib_brk | US30 | trend | 10 | 20% | -0.583 | -0.40 | -1.00 |
| dtfx_close_fib_brk | XAUUSD | std | 54 | 50% | +0.004 | -0.07 | +0.05 |
| dtfx_close_fib_brk | XAUUSD | trend | 13 | 23% | -0.434 | -0.70 | -0.27 |
| dtfx_close_origin | AUDUSD | std | 60 | 32% | -0.384 | -0.36 | -0.41 |
| dtfx_close_origin | AUDUSD | trend | 17 | 41% | -0.226 | -0.30 | -0.12 |
| dtfx_close_origin | EURUSD | std | 70 | 47% | -0.062 | -0.22 | +0.19 |
| dtfx_close_origin | EURUSD | trend | 18 | 28% | -0.268 | -0.52 | +0.13 |
| dtfx_close_origin | GBPUSD | std | 55 | 31% | -0.432 | -0.59 | -0.29 |
| dtfx_close_origin | GBPUSD | trend | 18 | 44% | +0.128 | -0.14 | +0.46 |
| dtfx_close_origin | NDQ | std | 65 | 48% | -0.046 | +0.16 | -0.25 |
| dtfx_close_origin | NDQ | trend | 17 | 24% | -0.262 | +0.24 | -0.83 |
| dtfx_close_origin | US30 | std | 84 | 38% | -0.276 | -0.47 | -0.09 |
| dtfx_close_origin | US30 | trend | 17 | 53% | +0.106 | -0.40 | +0.46 |
| dtfx_close_origin | XAUUSD | std | 65 | 52% | -0.009 | +0.06 | -0.08 |
| dtfx_close_origin | XAUUSD | trend | 16 | 19% | -0.593 | -0.52 | -0.67 |
| dtfx_wick_fib | AUDUSD | std | 106 | 30% | -0.408 | -0.47 | -0.34 |
| dtfx_wick_fib | AUDUSD | trend | 31 | 29% | -0.332 | -0.18 | -0.45 |
| dtfx_wick_fib | EURUSD | std | 87 | 43% | -0.170 | -0.36 | +0.06 |
| dtfx_wick_fib | EURUSD | trend | 17 | 29% | -0.115 | -0.30 | +0.22 |
| dtfx_wick_fib | GBPUSD | std | 90 | 43% | -0.200 | -0.38 | +0.03 |
| dtfx_wick_fib | GBPUSD | trend | 28 | 25% | -0.200 | -0.21 | -0.18 |
| dtfx_wick_fib | NDQ | std | 104 | 53% | -0.088 | -0.10 | -0.07 |
| dtfx_wick_fib | NDQ | trend | 25 | 56% | +0.184 | +0.04 | +0.37 |
| dtfx_wick_fib | US30 | std | 116 | 44% | -0.097 | -0.31 | +0.14 |
| dtfx_wick_fib | US30 | trend | 24 | 21% | -0.484 | -0.44 | -0.57 |
| dtfx_wick_fib | XAUUSD | std | 109 | 54% | +0.013 | -0.03 | +0.06 |
| dtfx_wick_fib | XAUUSD | trend | 30 | 40% | -0.082 | +0.16 | -0.40 |
| dtfx_zone | AUDUSD | std | 269 | 35% | -0.305 | -0.27 | -0.34 |
| dtfx_zone | AUDUSD | trend | 60 | 30% | -0.271 | -0.17 | -0.37 |
| dtfx_zone | EURUSD | std | 270 | 37% | -0.178 | -0.38 | +0.06 |
| dtfx_zone | EURUSD | trend | 52 | 31% | -0.311 | -0.52 | +0.00 |
| dtfx_zone | GBPUSD | std | 251 | 30% | -0.348 | -0.42 | -0.26 |
| dtfx_zone | GBPUSD | trend | 48 | 40% | +0.035 | -0.02 | +0.11 |
| dtfx_zone | NDQ | std | 255 | 48% | -0.062 | +0.04 | -0.17 |
| dtfx_zone | NDQ | trend | 51 | 41% | -0.108 | +0.12 | -0.29 |
| dtfx_zone | US30 | std | 258 | 43% | -0.140 | -0.22 | -0.06 |
| dtfx_zone | US30 | trend | 56 | 45% | +0.128 | -0.18 | +0.34 |
| dtfx_zone | XAUUSD | std | 249 | 43% | -0.205 | -0.19 | -0.22 |
| dtfx_zone | XAUUSD | trend | 52 | 40% | -0.244 | -0.21 | -0.26 |
| ict_2022 | AUDUSD | std | 28 | 61% | +0.169 | +0.19 | +0.15 |
| ict_2022 | AUDUSD | trend | 6 | 33% | +0.050 | +0.17 | -0.07 |
| ict_2022 | EURUSD | std | 34 | 44% | +0.099 | -0.13 | +0.39 |
| ict_2022 | EURUSD | trend | 6 | 50% | +0.582 | -0.05 | +1.21 |
| ict_2022 | GBPUSD | std | 40 | 38% | -0.356 | -0.32 | -0.39 |
| ict_2022 | GBPUSD | trend | 8 | 62% | +0.213 | -0.14 | +0.81 |
| ict_2022 | NDQ | std | 32 | 41% | -0.066 | -0.26 | +0.18 |
| ict_2022 | NDQ | trend | 8 | 50% | +0.070 | +0.03 | +0.09 |
| ict_2022 | US30 | std | 42 | 33% | -0.309 | -0.40 | -0.20 |
| ict_2022 | US30 | trend | 11 | 45% | +0.305 | -0.47 | +1.66 |
| ict_2022 | XAUUSD | std | 15 | 33% | -0.336 | -0.16 | -0.54 |
| ict_2022 | XAUUSD | trend | 5 | 20% | -0.592 | +0.36 | -0.83 |
| ict_amd | AUDUSD | std | 49 | 47% | -0.207 | -0.17 | -0.23 |
| ict_amd | AUDUSD | trend | 18 | 39% | -0.030 | -0.10 | -0.00 |
| ict_amd | EURUSD | std | 51 | 41% | -0.180 | -0.26 | -0.06 |
| ict_amd | EURUSD | trend | 20 | 40% | -0.110 | -0.40 | +0.24 |
| ict_amd | GBPUSD | std | 70 | 39% | -0.104 | -0.15 | -0.06 |
| ict_amd | GBPUSD | trend | 32 | 41% | +0.102 | +0.21 | -0.02 |
| ict_amd | NDQ | std | 35 | 46% | -0.007 | -0.18 | +0.11 |
| ict_amd | NDQ | trend | 18 | 39% | -0.034 | -0.22 | +0.11 |
| ict_amd | US30 | std | 82 | 51% | +0.048 | +0.05 | +0.05 |
| ict_amd | US30 | trend | 41 | 22% | -0.342 | -0.37 | -0.32 |
| ict_amd | XAUUSD | std | 45 | 51% | -0.081 | -0.33 | +0.03 |
| ict_amd | XAUUSD | trend | 16 | 56% | -0.138 | +0.24 | -0.19 |
| ict_fvg_sweep | AUDUSD | std | 58 | 34% | -0.357 | -0.28 | -0.44 |
| ict_fvg_sweep | AUDUSD | trend | 18 | 39% | -0.116 | -0.25 | +0.23 |
| ict_fvg_sweep | EURUSD | std | 44 | 50% | -0.026 | +0.01 | -0.07 |
| ict_fvg_sweep | EURUSD | trend | 14 | 36% | -0.041 | -0.33 | +0.67 |
| ict_fvg_sweep | GBPUSD | std | 60 | 43% | -0.226 | -0.25 | -0.17 |
| ict_fvg_sweep | GBPUSD | trend | 15 | 47% | +0.016 | -0.08 | +0.13 |
| ict_fvg_sweep | NDQ | std | 52 | 42% | -0.103 | +0.20 | -0.46 |
| ict_fvg_sweep | NDQ | trend | 11 | 18% | -0.503 | -0.09 | -1.00 |
| ict_fvg_sweep | US30 | std | 50 | 50% | +0.206 | -0.11 | +0.50 |
| ict_fvg_sweep | US30 | trend | 12 | 67% | +0.668 | -0.13 | +1.07 |
| ict_fvg_sweep | XAUUSD | std | 34 | 41% | -0.069 | -0.11 | -0.04 |
| ict_fvg_sweep | XAUUSD | trend | 9 | 22% | -0.123 | -0.60 | -0.06 |
| ict_ote | AUDUSD | std | 162 | 37% | -0.344 | -0.26 | -0.42 |
| ict_ote | AUDUSD | trend | 52 | 25% | -0.415 | -0.25 | -0.58 |
| ict_ote | EURUSD | std | 194 | 41% | -0.209 | -0.24 | -0.18 |
| ict_ote | EURUSD | trend | 60 | 28% | -0.304 | -0.49 | -0.08 |
| ict_ote | GBPUSD | std | 198 | 35% | -0.272 | -0.32 | -0.21 |
| ict_ote | GBPUSD | trend | 60 | 40% | -0.071 | -0.21 | +0.06 |
| ict_ote | NDQ | std | 171 | 43% | -0.140 | -0.10 | -0.19 |
| ict_ote | NDQ | trend | 52 | 38% | -0.209 | +0.10 | -0.51 |
| ict_ote | US30 | std | 185 | 43% | -0.072 | -0.35 | +0.15 |
| ict_ote | US30 | trend | 50 | 54% | +0.540 | +0.00 | +1.00 |
| ict_ote | XAUUSD | std | 161 | 51% | -0.020 | +0.07 | -0.11 |
| ict_ote | XAUUSD | trend | 43 | 40% | -0.171 | -0.23 | -0.13 |
| ict_silver_bullet | AUDUSD | std | 96 | 28% | -0.490 | -0.47 | -0.51 |
| ict_silver_bullet | AUDUSD | trend | 4 | 25% | -0.607 | -1.00 | -0.48 |
| ict_silver_bullet | EURUSD | std | 87 | 32% | -0.340 | -0.22 | -0.50 |
| ict_silver_bullet | EURUSD | trend | 2 | 50% | +0.087 | -0.29 | +0.46 |
| ict_silver_bullet | GBPUSD | std | 102 | 37% | -0.312 | -0.29 | -0.34 |
| ict_silver_bullet | GBPUSD | trend | 3 | 0% | -0.646 | — | -0.65 |
| ict_silver_bullet | NDQ | std | 89 | 45% | -0.082 | -0.25 | +0.11 |
| ict_silver_bullet | NDQ | trend | 3 | 0% | -0.830 | -0.75 | -1.00 |
| ict_silver_bullet | US30 | std | 76 | 39% | -0.202 | -0.25 | -0.13 |
| ict_silver_bullet | US30 | trend | 1 | 0% | -0.482 | -0.48 | — |
| ict_silver_bullet | XAUUSD | std | 83 | 49% | -0.029 | -0.24 | +0.16 |
| ict_turtle_soup | AUDUSD | std | 420 | 29% | -0.495 | -0.45 | -0.54 |
| ict_turtle_soup | AUDUSD | trend | 113 | 32% | -0.243 | -0.22 | -0.26 |
| ict_turtle_soup | EURUSD | std | 451 | 34% | -0.372 | -0.38 | -0.36 |
| ict_turtle_soup | EURUSD | trend | 104 | 33% | -0.159 | -0.28 | +0.00 |
| ict_turtle_soup | GBPUSD | std | 521 | 31% | -0.414 | -0.44 | -0.38 |
| ict_turtle_soup | GBPUSD | trend | 133 | 32% | -0.188 | -0.20 | -0.18 |
| ict_turtle_soup | NDQ | std | 494 | 48% | -0.081 | -0.13 | -0.03 |
| ict_turtle_soup | NDQ | trend | 90 | 32% | -0.206 | -0.24 | -0.18 |
| ict_turtle_soup | US30 | std | 620 | 45% | -0.103 | -0.23 | +0.03 |
| ict_turtle_soup | US30 | trend | 112 | 33% | -0.135 | -0.21 | -0.05 |
| ict_turtle_soup | XAUUSD | std | 533 | 42% | -0.129 | -0.11 | -0.14 |
| ict_turtle_soup | XAUUSD | trend | 112 | 35% | -0.023 | -0.20 | +0.11 |
| london_breakout | AUDUSD | std | 58 | 50% | -0.079 | -0.01 | -0.18 |
| london_breakout | AUDUSD | trend | 31 | 58% | +0.476 | +0.29 | +0.70 |
| london_breakout | EURUSD | std | 74 | 45% | -0.112 | -0.32 | +0.07 |
| london_breakout | EURUSD | trend | 37 | 59% | +0.333 | -0.19 | +0.73 |
| london_breakout | GBPUSD | std | 70 | 47% | -0.028 | +0.12 | -0.23 |
| london_breakout | GBPUSD | trend | 34 | 59% | +0.368 | +0.24 | +0.57 |
| london_breakout | NDQ | std | 47 | 53% | -0.019 | -0.04 | +0.01 |
| london_breakout | NDQ | trend | 21 | 52% | +0.397 | +1.11 | -0.38 |
| london_breakout | US30 | std | 86 | 44% | +0.044 | -0.11 | +0.21 |
| london_breakout | US30 | trend | 45 | 29% | -0.204 | -0.14 | -0.28 |
| london_breakout | XAUUSD | std | 48 | 67% | +0.206 | +0.31 | +0.15 |
| london_breakout | XAUUSD | trend | 24 | 54% | +0.540 | +1.10 | +0.26 |
| macd_cross | AUDUSD | std | 174 | 36% | -0.287 | -0.33 | -0.25 |
| macd_cross | AUDUSD | trend | 28 | 36% | -0.129 | -0.07 | -0.18 |
| macd_cross | EURUSD | std | 154 | 38% | -0.222 | -0.36 | -0.06 |
| macd_cross | EURUSD | trend | 31 | 39% | +0.023 | +0.08 | -0.02 |
| macd_cross | GBPUSD | std | 177 | 36% | -0.289 | -0.44 | -0.17 |
| macd_cross | GBPUSD | trend | 33 | 36% | +0.015 | +0.33 | -0.22 |
| macd_cross | NDQ | std | 137 | 45% | -0.019 | +0.04 | -0.06 |
| macd_cross | NDQ | trend | 27 | 37% | -0.096 | +0.01 | -0.18 |
| macd_cross | US30 | std | 145 | 50% | +0.112 | +0.06 | +0.16 |
| macd_cross | US30 | trend | 20 | 35% | -0.040 | -0.25 | +0.13 |
| macd_cross | XAUUSD | std | 143 | 46% | -0.054 | -0.06 | -0.05 |
| macd_cross | XAUUSD | trend | 43 | 35% | -0.210 | +0.01 | -0.33 |
| rsi_pullback | AUDUSD | std | 133 | 26% | -0.542 | -0.49 | -0.58 |
| rsi_pullback | AUDUSD | trend | 33 | 30% | -0.307 | +0.02 | -0.58 |
| rsi_pullback | EURUSD | std | 143 | 36% | -0.348 | -0.42 | -0.27 |
| rsi_pullback | EURUSD | trend | 38 | 26% | -0.319 | -0.18 | -0.45 |
| rsi_pullback | GBPUSD | std | 140 | 34% | -0.347 | -0.38 | -0.31 |
| rsi_pullback | GBPUSD | trend | 35 | 40% | -0.014 | -0.04 | +0.02 |
| rsi_pullback | NDQ | std | 121 | 49% | -0.028 | +0.09 | -0.14 |
| rsi_pullback | NDQ | trend | 37 | 27% | -0.220 | +0.03 | -0.37 |
| rsi_pullback | US30 | std | 149 | 53% | +0.019 | -0.04 | +0.07 |
| rsi_pullback | US30 | trend | 33 | 33% | +0.055 | -0.19 | +0.19 |
| rsi_pullback | XAUUSD | std | 119 | 48% | -0.017 | +0.16 | -0.21 |
| rsi_pullback | XAUUSD | trend | 28 | 61% | +0.734 | +0.74 | +0.73 |
| smc_bos_retest | AUDUSD | std | 262 | 34% | -0.306 | -0.18 | -0.42 |
| smc_bos_retest | AUDUSD | trend | 58 | 33% | -0.153 | +0.10 | -0.42 |
| smc_bos_retest | EURUSD | std | 245 | 35% | -0.126 | -0.33 | +0.08 |
| smc_bos_retest | EURUSD | trend | 63 | 46% | +0.230 | +0.14 | +0.32 |
| smc_bos_retest | GBPUSD | std | 214 | 36% | -0.293 | -0.29 | -0.30 |
| smc_bos_retest | GBPUSD | trend | 56 | 30% | -0.163 | +0.00 | -0.39 |
| smc_bos_retest | NDQ | std | 242 | 43% | -0.074 | -0.06 | -0.09 |
| smc_bos_retest | NDQ | trend | 53 | 43% | +0.060 | +0.28 | -0.16 |
| smc_bos_retest | US30 | std | 223 | 43% | -0.095 | -0.12 | -0.07 |
| smc_bos_retest | US30 | trend | 49 | 39% | -0.149 | -0.45 | +0.12 |
| smc_bos_retest | XAUUSD | std | 253 | 52% | +0.035 | -0.14 | +0.24 |
| smc_bos_retest | XAUUSD | trend | 52 | 37% | -0.143 | -0.23 | +0.00 |
| smc_breaker | AUDUSD | std | 106 | 29% | -0.408 | -0.42 | -0.39 |
| smc_breaker | AUDUSD | trend | 24 | 25% | -0.101 | -0.14 | -0.07 |
| smc_breaker | EURUSD | std | 108 | 24% | -0.521 | -0.52 | -0.53 |
| smc_breaker | EURUSD | trend | 22 | 18% | -0.476 | -0.47 | -0.50 |
| smc_breaker | GBPUSD | std | 117 | 22% | -0.558 | -0.47 | -0.64 |
| smc_breaker | GBPUSD | trend | 34 | 15% | -0.589 | -0.68 | -0.49 |
| smc_breaker | NDQ | std | 127 | 48% | -0.099 | -0.14 | -0.06 |
| smc_breaker | NDQ | trend | 16 | 44% | +0.011 | -0.39 | +0.19 |
| smc_breaker | US30 | std | 118 | 45% | -0.090 | -0.19 | -0.00 |
| smc_breaker | US30 | trend | 19 | 37% | -0.020 | -0.14 | +0.12 |
| smc_breaker | XAUUSD | std | 114 | 44% | -0.100 | -0.14 | -0.06 |
| smc_breaker | XAUUSD | trend | 33 | 42% | +0.030 | +0.64 | -0.27 |
| smc_choch | AUDUSD | std | 263 | 33% | -0.314 | -0.31 | -0.32 |
| smc_choch | AUDUSD | trend | 73 | 37% | -0.065 | +0.24 | -0.33 |
| smc_choch | EURUSD | std | 279 | 39% | -0.161 | -0.31 | +0.01 |
| smc_choch | EURUSD | trend | 59 | 31% | -0.177 | -0.51 | +0.21 |
| smc_choch | GBPUSD | std | 266 | 40% | -0.220 | -0.35 | -0.08 |
| smc_choch | GBPUSD | trend | 59 | 42% | +0.126 | +0.22 | +0.02 |
| smc_choch | NDQ | std | 261 | 49% | +0.000 | -0.02 | +0.03 |
| smc_choch | NDQ | trend | 40 | 50% | +0.090 | +0.05 | +0.15 |
| smc_choch | US30 | std | 266 | 48% | +0.019 | +0.05 | -0.00 |
| smc_choch | US30 | trend | 58 | 33% | -0.142 | -0.30 | +0.04 |
| smc_choch | XAUUSD | std | 278 | 52% | +0.003 | -0.03 | +0.03 |
| smc_choch | XAUUSD | trend | 63 | 43% | -0.049 | -0.04 | -0.06 |
| smc_displacement | AUDUSD | std | 131 | 29% | -0.448 | -0.42 | -0.48 |
| smc_displacement | AUDUSD | trend | 32 | 28% | -0.309 | -0.09 | -0.56 |
| smc_displacement | EURUSD | std | 128 | 39% | -0.264 | -0.26 | -0.26 |
| smc_displacement | EURUSD | trend | 26 | 23% | -0.278 | -0.22 | -0.31 |
| smc_displacement | GBPUSD | std | 124 | 31% | -0.321 | -0.41 | -0.25 |
| smc_displacement | GBPUSD | trend | 30 | 30% | -0.138 | -0.42 | +0.19 |
| smc_displacement | NDQ | std | 106 | 47% | -0.070 | -0.05 | -0.09 |
| smc_displacement | NDQ | trend | 17 | 41% | +0.078 | +0.07 | +0.10 |
| smc_displacement | US30 | std | 106 | 51% | +0.198 | +0.17 | +0.23 |
| smc_displacement | US30 | trend | 16 | 31% | -0.139 | +0.16 | -0.37 |
| smc_displacement | XAUUSD | std | 101 | 52% | +0.002 | -0.08 | +0.07 |
| smc_displacement | XAUUSD | trend | 21 | 43% | -0.194 | -0.19 | -0.20 |
| smc_ifvg | AUDUSD | std | 565 | 26% | -0.541 | -0.53 | -0.55 |
| smc_ifvg | AUDUSD | trend | 91 | 23% | -0.388 | -0.32 | -0.45 |
| smc_ifvg | EURUSD | std | 492 | 26% | -0.495 | -0.55 | -0.44 |
| smc_ifvg | EURUSD | trend | 89 | 36% | -0.042 | +0.06 | -0.11 |
| smc_ifvg | GBPUSD | std | 446 | 27% | -0.519 | -0.56 | -0.47 |
| smc_ifvg | GBPUSD | trend | 65 | 25% | -0.271 | -0.57 | +0.15 |
| smc_ifvg | NDQ | std | 388 | 47% | -0.038 | +0.05 | -0.13 |
| smc_ifvg | NDQ | trend | 62 | 29% | -0.116 | +0.24 | -0.47 |
| smc_ifvg | US30 | std | 455 | 44% | -0.123 | -0.19 | -0.06 |
| smc_ifvg | US30 | trend | 61 | 30% | -0.089 | -0.20 | +0.01 |
| smc_ifvg | XAUUSD | std | 384 | 52% | +0.019 | -0.10 | +0.12 |
| smc_ifvg | XAUUSD | trend | 68 | 44% | +0.177 | +0.36 | +0.04 |
| smc_liquidity_sweep | AUDUSD | std | 44 | 39% | -0.177 | -0.35 | -0.07 |
| smc_liquidity_sweep | AUDUSD | trend | 32 | 31% | -0.193 | -0.07 | -0.29 |
| smc_liquidity_sweep | EURUSD | std | 32 | 28% | -0.411 | -0.51 | -0.32 |
| smc_liquidity_sweep | EURUSD | trend | 20 | 35% | -0.295 | -0.56 | -0.03 |
| smc_liquidity_sweep | GBPUSD | std | 51 | 35% | -0.254 | -0.04 | -0.50 |
| smc_liquidity_sweep | GBPUSD | trend | 28 | 32% | -0.156 | +0.25 | -0.70 |
| smc_liquidity_sweep | NDQ | std | 33 | 48% | -0.172 | -0.04 | -0.27 |
| smc_liquidity_sweep | NDQ | trend | 21 | 38% | -0.270 | -0.47 | -0.15 |
| smc_liquidity_sweep | US30 | std | 57 | 44% | -0.125 | -0.04 | -0.21 |
| smc_liquidity_sweep | US30 | trend | 31 | 23% | -0.276 | -0.18 | -0.37 |
| smc_liquidity_sweep | XAUUSD | std | 25 | 40% | -0.214 | -0.48 | -0.04 |
| smc_liquidity_sweep | XAUUSD | trend | 15 | 47% | -0.014 | +0.12 | -0.06 |
| smc_mss | AUDUSD | std | 105 | 36% | -0.297 | -0.21 | -0.36 |
| smc_mss | AUDUSD | trend | 30 | 40% | -0.073 | +0.59 | -0.46 |
| smc_mss | EURUSD | std | 103 | 47% | -0.062 | +0.00 | -0.14 |
| smc_mss | EURUSD | trend | 18 | 50% | +0.018 | -0.30 | +0.65 |
| smc_mss | GBPUSD | std | 125 | 38% | -0.207 | -0.01 | -0.34 |
| smc_mss | GBPUSD | trend | 36 | 42% | -0.011 | +0.09 | -0.14 |
| smc_mss | NDQ | std | 82 | 44% | -0.031 | -0.12 | +0.05 |
| smc_mss | NDQ | trend | 20 | 35% | -0.127 | -0.42 | -0.00 |
| smc_mss | US30 | std | 118 | 47% | -0.008 | -0.16 | +0.13 |
| smc_mss | US30 | trend | 24 | 42% | +0.019 | +0.13 | -0.06 |
| smc_mss | XAUUSD | std | 84 | 57% | +0.073 | +0.06 | +0.09 |
| smc_mss | XAUUSD | trend | 16 | 44% | -0.138 | +0.40 | -0.46 |
| smc_order_block | AUDUSD | std | 237 | 26% | -0.542 | -0.46 | -0.61 |
| smc_order_block | AUDUSD | trend | 45 | 27% | -0.249 | -0.03 | -0.53 |
| smc_order_block | EURUSD | std | 231 | 29% | -0.494 | -0.59 | -0.40 |
| smc_order_block | EURUSD | trend | 48 | 40% | -0.016 | -0.49 | +0.24 |
| smc_order_block | GBPUSD | std | 230 | 24% | -0.593 | -0.55 | -0.64 |
| smc_order_block | GBPUSD | trend | 51 | 20% | -0.519 | -0.50 | -0.53 |
| smc_order_block | NDQ | std | 195 | 41% | -0.204 | -0.09 | -0.34 |
| smc_order_block | NDQ | trend | 38 | 34% | -0.104 | +0.20 | -0.44 |
| smc_order_block | US30 | std | 214 | 36% | -0.278 | -0.26 | -0.30 |
| smc_order_block | US30 | trend | 33 | 27% | -0.235 | -0.24 | -0.23 |
| smc_order_block | XAUUSD | std | 235 | 45% | -0.116 | -0.16 | -0.08 |
| smc_order_block | XAUUSD | trend | 52 | 33% | -0.158 | -0.32 | -0.04 |
| smt_divergence | NDQ | std | 89 | 47% | -0.050 | +0.08 | -0.24 |
| smt_divergence | NDQ | trend | 22 | 32% | +0.045 | +0.41 | -0.32 |
| smt_divergence | US30 | std | 95 | 42% | +0.013 | +0.35 | -0.38 |
| smt_divergence | US30 | trend | 25 | 28% | -0.365 | -0.26 | -0.47 |
| sr_rejection | AUDUSD | std | 617 | 24% | -0.604 | -0.59 | -0.62 |
| sr_rejection | AUDUSD | trend | 120 | 32% | -0.145 | -0.18 | -0.11 |
| sr_rejection | EURUSD | std | 550 | 30% | -0.470 | -0.56 | -0.37 |
| sr_rejection | EURUSD | trend | 112 | 29% | -0.282 | -0.45 | -0.12 |
| sr_rejection | GBPUSD | std | 674 | 26% | -0.521 | -0.60 | -0.44 |
| sr_rejection | GBPUSD | trend | 122 | 25% | -0.321 | -0.49 | -0.15 |
| sr_rejection | NDQ | std | 659 | 44% | -0.133 | -0.15 | -0.12 |
| sr_rejection | NDQ | trend | 115 | 37% | -0.035 | -0.09 | +0.04 |
| sr_rejection | US30 | std | 555 | 44% | -0.161 | -0.21 | -0.11 |
| sr_rejection | US30 | trend | 97 | 41% | +0.135 | +0.28 | +0.04 |
| sr_rejection | XAUUSD | std | 730 | 44% | -0.129 | -0.16 | -0.10 |
| sr_rejection | XAUUSD | trend | 138 | 33% | -0.079 | -0.03 | -0.11 |
| stoic_sbs | AUDUSD | std | 20 | 35% | -0.365 | -0.01 | -0.66 |
| stoic_sbs | AUDUSD | trend | 5 | 40% | +0.051 | +0.20 | -0.17 |
| stoic_sbs | EURUSD | std | 15 | 47% | +0.069 | +0.44 | -0.35 |
| stoic_sbs | EURUSD | trend | 4 | 25% | -0.255 | -1.00 | -0.01 |
| stoic_sbs | GBPUSD | std | 13 | 46% | -0.166 | -0.11 | -0.23 |
| stoic_sbs | GBPUSD | trend | 3 | 33% | +0.219 | +1.65 | -0.50 |
| stoic_sbs | NDQ | std | 14 | 43% | -0.272 | -0.18 | -0.44 |
| stoic_sbs | NDQ | trend | 1 | 0% | -1.000 | — | -1.00 |
| stoic_sbs | US30 | std | 11 | 64% | +0.136 | +0.02 | +0.18 |
| stoic_sbs | XAUUSD | std | 23 | 65% | +0.162 | -0.30 | +0.46 |
| stoic_sbs | XAUUSD | trend | 4 | 75% | +0.540 | +0.04 | +0.71 |
| trend_breakout | AUDUSD | std | 84 | 37% | -0.353 | -0.41 | -0.30 |
| trend_breakout | AUDUSD | trend | 84 | 30% | -0.276 | -0.23 | -0.32 |
| trend_breakout | EURUSD | std | 76 | 42% | -0.033 | -0.17 | +0.06 |
| trend_breakout | EURUSD | trend | 76 | 33% | -0.069 | -0.02 | -0.10 |
| trend_breakout | GBPUSD | std | 76 | 34% | -0.295 | -0.22 | -0.37 |
| trend_breakout | GBPUSD | trend | 75 | 27% | -0.202 | -0.04 | -0.36 |
| trend_breakout | NDQ | std | 62 | 42% | -0.091 | +0.02 | -0.23 |
| trend_breakout | NDQ | trend | 62 | 35% | +0.025 | +0.11 | -0.09 |
| trend_breakout | US30 | std | 56 | 50% | +0.019 | +0.05 | -0.00 |
| trend_breakout | US30 | trend | 54 | 31% | -0.175 | -0.08 | -0.23 |
| trend_breakout | XAUUSD | std | 68 | 46% | -0.097 | -0.16 | -0.02 |
| trend_breakout | XAUUSD | trend | 67 | 34% | -0.116 | -0.04 | -0.21 |
| trend_pullback | AUDUSD | std | 32 | 50% | -0.135 | -0.20 | -0.08 |
| trend_pullback | AUDUSD | trend | 31 | 29% | -0.341 | -0.58 | -0.14 |
| trend_pullback | EURUSD | std | 36 | 33% | -0.296 | -0.26 | -0.31 |
| trend_pullback | EURUSD | trend | 34 | 21% | -0.416 | -0.56 | -0.35 |
| trend_pullback | GBPUSD | std | 37 | 32% | -0.322 | -0.63 | -0.03 |
| trend_pullback | GBPUSD | trend | 36 | 25% | -0.315 | -0.57 | -0.06 |
| trend_pullback | NDQ | std | 46 | 59% | +0.152 | +0.20 | +0.09 |
| trend_pullback | NDQ | trend | 42 | 52% | +0.275 | +0.30 | +0.24 |
| trend_pullback | US30 | std | 20 | 55% | +0.191 | -0.18 | +0.56 |
| trend_pullback | US30 | trend | 19 | 32% | -0.046 | -0.08 | -0.01 |
| trend_pullback | XAUUSD | std | 19 | 32% | -0.371 | -0.41 | -0.33 |
| trend_pullback | XAUUSD | trend | 19 | 21% | -0.567 | -0.77 | -0.34 |
| vwap | AUDUSD | std | 255 | 24% | -0.537 | -0.56 | -0.52 |
| vwap | AUDUSD | trend | 85 | 28% | -0.357 | -0.40 | -0.30 |
| vwap | EURUSD | std | 321 | 27% | -0.486 | -0.58 | -0.39 |
| vwap | EURUSD | trend | 91 | 22% | -0.378 | -0.38 | -0.38 |
| vwap | GBPUSD | std | 281 | 29% | -0.468 | -0.50 | -0.43 |
| vwap | GBPUSD | trend | 92 | 22% | -0.473 | -0.52 | -0.40 |
| vwap | NDQ | std | 239 | 48% | +0.005 | -0.03 | +0.05 |
| vwap | NDQ | trend | 73 | 44% | +0.130 | +0.10 | +0.16 |
| vwap | US30 | std | 302 | 45% | -0.069 | -0.26 | +0.14 |
| vwap | US30 | trend | 98 | 32% | -0.138 | -0.27 | -0.01 |
| vwap | XAUUSD | std | 230 | 47% | -0.071 | -0.03 | -0.11 |
| vwap | XAUUSD | trend | 62 | 35% | +0.006 | -0.15 | +0.17 |
| zone_confluence | AUDUSD | std | 163 | 34% | -0.401 | -0.36 | -0.44 |
| zone_confluence | AUDUSD | trend | 38 | 24% | -0.326 | -0.41 | -0.18 |
| zone_confluence | EURUSD | std | 183 | 38% | -0.294 | -0.32 | -0.27 |
| zone_confluence | EURUSD | trend | 49 | 39% | -0.107 | -0.38 | +0.13 |
| zone_confluence | GBPUSD | std | 174 | 32% | -0.419 | -0.47 | -0.37 |
| zone_confluence | GBPUSD | trend | 49 | 33% | -0.286 | -0.46 | -0.12 |
| zone_confluence | NDQ | std | 151 | 45% | -0.099 | -0.01 | -0.20 |
| zone_confluence | NDQ | trend | 34 | 26% | -0.446 | -0.04 | -0.81 |
| zone_confluence | US30 | std | 156 | 40% | -0.054 | -0.30 | +0.17 |
| zone_confluence | US30 | trend | 30 | 43% | +0.132 | -0.17 | +0.39 |
| zone_confluence | XAUUSD | std | 136 | 47% | -0.022 | -0.01 | -0.03 |
| zone_confluence | XAUUSD | trend | 37 | 43% | -0.020 | -0.03 | -0.02 |

## 3b · Exits compared (same signals, default variants, all instruments, 15m+ for trend)

std = 1R first target, half banked, runner trailed (the bot today) · scalp = all out at 1R, 30-min cap (≤5m) · trend = 2R first target + runner · tpX = all out at X R, no runner

| exit | trades | win | avg R | total R | per symbol (avg R) |
|---|---|---|---|---|---|
| scalp | 21559 | 37% | -0.251 | -5410 | AUDUSD -0.456 · EURUSD -0.382 · GBPUSD -0.421 · NDQ -0.073 · US30 -0.115 · XAUUSD -0.066 |
| std | 27516 | 39% | -0.228 | -6287 | AUDUSD -0.437 · EURUSD -0.315 · GBPUSD -0.388 · NDQ -0.074 · US30 -0.083 · XAUUSD -0.062 |
| tp1 | 27898 | 39% | -0.223 | -6229 | AUDUSD -0.401 · EURUSD -0.320 · GBPUSD -0.375 · NDQ -0.069 · US30 -0.109 · XAUUSD -0.054 |
| tp1.5 | 27477 | 33% | -0.223 | -6138 | AUDUSD -0.412 · EURUSD -0.307 · GBPUSD -0.378 · NDQ -0.074 · US30 -0.103 · XAUUSD -0.054 |
| tp2 | 27139 | 30% | -0.222 | -6018 | AUDUSD -0.434 · EURUSD -0.294 · GBPUSD -0.371 · NDQ -0.074 · US30 -0.095 · XAUUSD -0.050 |
| trend | 6667 | 34% | -0.128 | -853 | AUDUSD -0.234 · EURUSD -0.153 · GBPUSD -0.177 · NDQ -0.051 · US30 -0.062 · XAUUSD -0.063 |

## 4 · Best cell per setup (≥30 trades, by t-stat)

| setup | variant | sym | tf | exit | trades | win | avg R | t | quarters positive |
|---|---|---|---|---|---|---|---|---|---|
| smc_mss | default | XAUUSD | 3min | tp1.5 | 39 | 64% | +0.547 | 2.8 | 4/4 |
| dtfx_wick_fib | level=50-70 | NDQ | 15min | std | 41 | 71% | +0.357 | 2.4 | 4/4 |
| smc_ifvg | default | XAUUSD | 15min | tp1 | 42 | 67% | +0.335 | 2.3 | 4/4 |
| dtfx_close_fib | sessions=killzones | US30 | 1min | std | 53 | 62% | +0.504 | 2.2 | 3/4 |
| smc_displacement | default | US30 | 5min | std | 31 | 61% | +0.733 | 2.1 | 4/4 |
| ict_turtle_soup | confirm=choch | XAUUSD | 3min | tp1.5 | 47 | 60% | +0.347 | 2.1 | 4/4 |
| ict_amd | model=midnight | US30 | 15min | std | 34 | 62% | +0.355 | 1.7 | 4/4 |
| vwap | mode=reclaim | XAUUSD | 5min | scalp | 118 | 53% | +0.125 | 1.7 | 4/4 |
| smc_choch | vol=impulse | XAUUSD | 1min | tp1.5 | 109 | 49% | +0.196 | 1.7 | 4/4 |
| macd_cross | default | US30 | 3min | scalp | 82 | 59% | +0.134 | 1.6 | 3/4 |
| dtfx_close_fib_brk | vol=dry | XAUUSD | 1min | std | 35 | 63% | +0.333 | 1.6 | 3/4 |
| sr_rejection | default | NDQ | 30min | tp2 | 32 | 53% | +0.301 | 1.5 | 4/4 |
| smc_bos_retest | stop=level | NDQ | 15min | trend | 31 | 45% | +0.386 | 1.5 | 3/4 |
| ict_2022 | max_wait=20 | XAUUSD | 1min | tp2 | 33 | 42% | +0.333 | 1.2 | 3/4 |
| dtfx_close_origin | confirm=touch | NDQ | 5min | tp2 | 133 | 40% | +0.145 | 1.2 | 3/4 |
| smt_divergence | default | NDQ | 1min | scalp | 110 | 55% | +0.098 | 1.1 | 3/4 |
| trend_breakout | trend=structure | XAUUSD | 15min | tp1 | 38 | 61% | +0.165 | 1.1 | 4/4 |
| ict_silver_bullet | sb=am_pm | NDQ | 3min | scalp | 36 | 50% | +0.173 | 1.0 | 3/4 |
| dtfx_zone | default | NDQ | 3min | tp2 | 115 | 43% | +0.121 | 1.0 | 3/4 |
| rsi_pullback | default | NDQ | 3min | tp2 | 51 | 41% | +0.184 | 0.9 | 3/4 |
| ict_ote | default | US30 | 15min | trend | 30 | 40% | +0.171 | 0.7 | 2/4 |
| smc_breaker | default | US30 | 5min | tp2 | 37 | 38% | +0.110 | 0.5 | 3/4 |
| zone_confluence | default | XAUUSD | 5min | std | 35 | 46% | +0.098 | 0.4 | 2/4 |
| smc_order_block | default | NDQ | 5min | tp2 | 63 | 33% | -0.034 | -0.2 | 2/4 |
