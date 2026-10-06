# Strategy test — 365 days

Created 2026-10-06 15:49 NY · trades 2025-10-06 → 2026-10-06 · 788,198 simulated trades · 3,728 cells

R is per trade in units of its own risk, after spread. Quarters split the period in four equal parts; an edge worth trading is positive in most quarters, not just on average. 1-minute cells are listed but the playbook doesn't trade 1m (spread is too large a share of the bar).

## 1 · The playbook system, replayed week by week on unseen data

Each week: pick cells from the trailing 60 days, trade them the next week, capacity rules on. This is the number that says whether the approach works.

- trades **1454**, win rate **50%**, avg **-0.000R**, total **-0.30R**, profit factor 1.0, worst drawdown -20.18R, t-stat -0.01, chance it's really ≤0: 0.522
- without the 3 best trades: -13.41R
- XAUUSD: 1358 trades, 50% win, -10.30R
- NDQ: 96 trades, 62% win, +9.99R

By month (R): 2025-11 +1.2 (161) · 2025-12 -19.0 (171) · 2026-01 -5.1 (146) · 2026-02 -13.0 (68) · 2026-03 -6.3 (129) · 2026-04 +15.7 (115) · 2026-05 -5.2 (102) · 2026-06 +6.8 (201) · 2026-07 -10.5 (116) · 2026-08 -9.9 (104) · 2026-09 +15.3 (129) · 2026-10 +3.4 (12)

Positive weeks: 23 of 49

## 2 · Cells that held up (≥30 trades, positive in both halves and ≥3 of 4 quarters)

| setup | variant | sym | tf | exit | trades | win | avg R | t | H1 | H2 | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| smc_displacement | disp_k=1.0 | XAUUSD | 15min | std | 67 | 66% | +0.279 | 2.5 | +0.37 | +0.13 | +0.29 | +0.49 | +0.06 | +0.23 |
| vwap | vol=dry | XAUUSD | 15min | std | 84 | 61% | +0.319 | 2.5 | +0.34 | +0.30 | +0.21 | +0.45 | +0.45 | +0.18 |
| vwap | vol=dry | NDQ | 30min | std | 30 | 77% | +0.377 | 2.4 | +0.28 | +0.46 | +0.26 | +0.31 | +0.44 | +0.49 |
| rsi_pullback | default | XAUUSD | 15min | std | 79 | 63% | +0.255 | 2.4 | +0.26 | +0.25 | +0.35 | +0.12 | -0.20 | +0.75 |
| smc_displacement | swing=3 | XAUUSD | 15min | std | 45 | 69% | +0.325 | 2.3 | +0.42 | +0.16 | +0.32 | +0.63 | +0.21 | +0.13 |
| dtfx_wick_fib | vol=impulse | XAUUSD | 3min | scalp | 65 | 68% | +0.229 | 2.3 | +0.19 | +0.30 | +0.20 | +0.17 | +0.59 | +0.07 |
| dtfx_close_fib | vol=impulse | XAUUSD | 3min | scalp | 44 | 70% | +0.268 | 2.3 | +0.29 | +0.23 | +0.54 | +0.04 | +0.55 | -0.02 |
| dtfx_close_fib | mtf=1h | NDQ | 5min | scalp | 59 | 66% | +0.170 | 2.3 | +0.30 | +0.03 | +0.45 | +0.19 | +0.04 | +0.02 |
| smc_displacement | default | XAUUSD | 15min | std | 49 | 67% | +0.299 | 2.2 | +0.47 | +0.03 | +0.31 | +0.84 | +0.03 | +0.04 |
| ict_amd | manip=ny | NDQ | 3min | scalp | 39 | 67% | +0.165 | 2.1 | +0.21 | +0.11 | +0.14 | +0.28 | +0.09 | +0.16 |
| smc_ifvg | default | XAUUSD | 15min | std | 154 | 60% | +0.161 | 2.1 | +0.10 | +0.22 | -0.01 | +0.21 | +0.26 | +0.18 |
| smc_displacement | disp_k=1.5 | XAUUSD | 15min | std | 30 | 70% | +0.326 | 2.0 | +0.46 | +0.17 | +0.23 | +1.15 | +0.21 | +0.14 |
| ict_turtle_soup | level=session | US30 | 15min | std | 62 | 58% | +0.342 | 2.0 | +0.44 | +0.21 | +0.40 | +0.48 | +0.60 | -0.24 |
| dtfx_wick_fib | swing=5 | NDQ | 3min | scalp | 138 | 64% | +0.127 | 2.0 | +0.23 | +0.02 | +0.13 | +0.31 | +0.13 | -0.10 |
| dtfx_close_fib_brk | vol=impulse | US30 | 1min | std | 102 | 61% | +0.242 | 2.0 | +0.18 | +0.31 | -0.14 | +0.50 | +0.16 | +0.40 |
| dtfx_zone | default | NDQ | 30min | std | 55 | 64% | +0.162 | 2.0 | +0.15 | +0.18 | +0.05 | +0.28 | +0.35 | -0.01 |
| dtfx_wick_fib | default | NDQ | 3min | scalp | 228 | 61% | +0.097 | 1.9 | +0.15 | +0.04 | +0.07 | +0.24 | -0.01 | +0.08 |
| dtfx_zone | default | NDQ | 1h | std | 33 | 58% | +0.149 | 1.8 | +0.21 | +0.08 | +0.10 | +0.34 | +0.18 | -0.05 |
| smc_displacement | stop=fvg_bot | XAUUSD | 15min | std | 50 | 62% | +0.275 | 1.8 | +0.36 | +0.15 | +0.25 | +0.61 | +0.09 | +0.19 |
| smc_choch | swing=2 | NDQ | 1h | std | 38 | 61% | +0.148 | 1.8 | +0.22 | +0.05 | +0.15 | +0.29 | +0.04 | +0.06 |
| dtfx_close_fib_brk | vol=climax | US30 | 1min | scalp | 36 | 67% | +0.256 | 1.7 | +0.28 | +0.20 | +0.07 | +0.37 | +0.06 | +0.30 |
| ict_amd | manip=ny | NDQ | 3min | std | 39 | 56% | +0.270 | 1.7 | +0.40 | +0.12 | +0.32 | +0.48 | +0.16 | +0.05 |
| dtfx_close_fib_brk | vol=impulse | US30 | 1min | scalp | 103 | 60% | +0.163 | 1.7 | +0.16 | +0.17 | -0.00 | +0.32 | +0.19 | +0.16 |
| dtfx_wick_fib | mtf=1h | NDQ | 5min | scalp | 91 | 62% | +0.119 | 1.7 | +0.19 | +0.06 | +0.24 | +0.13 | +0.17 | -0.06 |
| dtfx_wick_fib | mtf=1h | NDQ | 3min | scalp | 161 | 61% | +0.101 | 1.7 | +0.18 | +0.02 | +0.12 | +0.26 | -0.14 | +0.18 |
| dtfx_wick_fib | vol=impulse | XAUUSD | 3min | std | 63 | 60% | +0.220 | 1.7 | +0.30 | +0.10 | +0.06 | +0.56 | +0.40 | -0.14 |
| ict_amd | vol=dry | US30 | 5min | scalp | 53 | 55% | +0.135 | 1.6 | +0.05 | +0.22 | +0.14 | -0.09 | +0.12 | +0.30 |
| smc_displacement | entry=top | XAUUSD | 3min | scalp | 313 | 55% | +0.074 | 1.6 | +0.08 | +0.06 | +0.10 | +0.07 | +0.03 | +0.11 |
| ict_amd | model=midnight | XAUUSD | 30min | std | 91 | 55% | +0.111 | 1.6 | +0.06 | +0.17 | -0.02 | +0.17 | +0.12 | +0.21 |
| smc_choch | swing=5 | XAUUSD | 15min | std | 88 | 52% | +0.117 | 1.6 | +0.08 | +0.15 | +0.08 | +0.09 | +0.31 | -0.02 |
| ict_2022 | vol=impulse | XAUUSD | 1min | std | 34 | 56% | +0.500 | 1.6 | +1.20 | +0.12 | +1.06 | +1.27 | +0.03 | +0.19 |
| vwap | vol=impulse | US30 | 15min | std | 55 | 53% | +0.261 | 1.5 | +0.34 | +0.21 | +0.48 | +0.23 | -0.14 | +0.43 |
| ict_amd | manip=london | XAUUSD | 15min | std | 30 | 57% | +0.260 | 1.5 | +0.25 | +0.31 | +0.29 | +0.18 | +1.06 | +0.00 |
| dtfx_close_origin | vol=impulse | US30 | 1min | std | 102 | 56% | +0.212 | 1.5 | +0.16 | +0.28 | +0.12 | +0.18 | +0.08 | +0.44 |
| vwap | default | XAUUSD | 1h | std | 43 | 60% | +0.223 | 1.5 | +0.40 | +0.02 | +0.28 | +0.55 | +0.16 | -0.22 |
| ict_amd | manip=ny | NDQ | 1min | scalp | 43 | 67% | +0.127 | 1.4 | +0.02 | +0.26 | -0.11 | +0.21 | +0.15 | +0.38 |
| vwap | default | NDQ | 1h | std | 51 | 59% | +0.184 | 1.4 | +0.04 | +0.30 | -0.15 | +0.22 | +0.30 | +0.28 |
| dtfx_close_origin | vol=impulse | US30 | 1min | scalp | 104 | 55% | +0.149 | 1.4 | +0.19 | +0.10 | +0.26 | +0.14 | +0.16 | +0.05 |
| dtfx_close_fib | swing=5 | XAUUSD | 5min | std | 64 | 66% | +0.164 | 1.4 | +0.07 | +0.30 | -0.15 | +0.21 | +0.54 | +0.13 |
| ict_amd | default | XAUUSD | 15min | std | 35 | 54% | +0.209 | 1.4 | +0.21 | +0.20 | +0.26 | +0.14 | +0.68 | -0.01 |

144 cells qualify out of 2652 with ≥30 trades. With this many cells, a few will pass by luck alone — a t above ~3 is the bar for 'probably real'.

## 3 · Every setup, overall (default variant, standard exits, all timeframes but 1m)

| setup | sym | trades | win | avg R | first half | second half |
|---|---|---|---|---|---|---|
| dtfx_close_fib | NDQ | 293 | 52% | -0.036 | -0.00 | -0.08 |
| dtfx_close_fib | US30 | 288 | 45% | -0.079 | -0.02 | -0.13 |
| dtfx_close_fib | XAUUSD | 318 | 51% | +0.002 | -0.02 | +0.03 |
| dtfx_close_fib_brk | NDQ | 223 | 51% | -0.056 | -0.01 | -0.10 |
| dtfx_close_fib_brk | US30 | 228 | 45% | -0.090 | +0.04 | -0.21 |
| dtfx_close_fib_brk | XAUUSD | 258 | 48% | -0.078 | -0.18 | +0.03 |
| dtfx_close_origin | NDQ | 265 | 49% | -0.025 | -0.04 | -0.01 |
| dtfx_close_origin | US30 | 331 | 46% | -0.099 | -0.02 | -0.17 |
| dtfx_close_origin | XAUUSD | 309 | 43% | -0.170 | -0.18 | -0.15 |
| dtfx_wick_fib | NDQ | 459 | 52% | -0.021 | -0.01 | -0.04 |
| dtfx_wick_fib | US30 | 428 | 49% | -0.025 | -0.01 | -0.04 |
| dtfx_wick_fib | XAUUSD | 459 | 53% | +0.031 | +0.06 | -0.01 |
| dtfx_zone | NDQ | 1047 | 49% | -0.053 | -0.11 | +0.00 |
| dtfx_zone | US30 | 1025 | 44% | -0.133 | -0.14 | -0.13 |
| dtfx_zone | XAUUSD | 1035 | 49% | -0.048 | +0.02 | -0.12 |
| ict_2022 | NDQ | 142 | 39% | -0.186 | -0.29 | -0.06 |
| ict_2022 | US30 | 152 | 39% | -0.212 | -0.13 | -0.29 |
| ict_2022 | XAUUSD | 99 | 44% | -0.140 | -0.09 | -0.19 |
| ict_amd | NDQ | 264 | 47% | -0.007 | -0.08 | +0.09 |
| ict_amd | US30 | 347 | 45% | -0.019 | -0.03 | -0.01 |
| ict_amd | XAUUSD | 182 | 52% | +0.011 | +0.06 | -0.07 |
| ict_fvg_sweep | NDQ | 193 | 44% | -0.141 | -0.36 | +0.03 |
| ict_fvg_sweep | US30 | 224 | 48% | +0.031 | -0.06 | +0.13 |
| ict_fvg_sweep | XAUUSD | 168 | 45% | -0.090 | -0.10 | -0.08 |
| ict_ote | NDQ | 746 | 49% | -0.033 | -0.13 | +0.05 |
| ict_ote | US30 | 777 | 44% | -0.086 | -0.06 | -0.12 |
| ict_ote | XAUUSD | 697 | 49% | -0.053 | -0.09 | -0.01 |
| ict_silver_bullet | NDQ | 321 | 45% | -0.057 | -0.17 | +0.03 |
| ict_silver_bullet | US30 | 364 | 47% | -0.059 | -0.03 | -0.09 |
| ict_silver_bullet | XAUUSD | 336 | 45% | -0.076 | -0.11 | -0.03 |
| ict_turtle_soup | NDQ | 2122 | 46% | -0.083 | -0.10 | -0.07 |
| ict_turtle_soup | US30 | 2267 | 45% | -0.106 | -0.14 | -0.07 |
| ict_turtle_soup | XAUUSD | 1988 | 46% | -0.086 | -0.09 | -0.08 |
| london_breakout | NDQ | 241 | 44% | -0.148 | -0.26 | -0.04 |
| london_breakout | US30 | 299 | 44% | -0.087 | -0.26 | +0.06 |
| london_breakout | XAUUSD | 177 | 47% | -0.063 | -0.14 | -0.01 |
| macd_cross | NDQ | 604 | 48% | +0.011 | -0.03 | +0.05 |
| macd_cross | US30 | 600 | 48% | -0.038 | -0.10 | +0.01 |
| macd_cross | XAUUSD | 602 | 47% | -0.054 | -0.02 | -0.10 |
| rsi_pullback | NDQ | 577 | 46% | -0.127 | -0.16 | -0.10 |
| rsi_pullback | US30 | 574 | 45% | -0.115 | -0.21 | -0.03 |
| rsi_pullback | XAUUSD | 483 | 53% | +0.036 | +0.03 | +0.04 |
| smc_bos_retest | NDQ | 996 | 47% | -0.042 | -0.08 | -0.01 |
| smc_bos_retest | US30 | 971 | 45% | -0.084 | -0.08 | -0.08 |
| smc_bos_retest | XAUUSD | 1035 | 49% | +0.008 | +0.01 | +0.01 |
| smc_breaker | NDQ | 486 | 41% | -0.201 | -0.27 | -0.12 |
| smc_breaker | US30 | 471 | 44% | -0.111 | -0.15 | -0.07 |
| smc_breaker | XAUUSD | 426 | 47% | -0.044 | -0.07 | -0.02 |
| smc_choch | NDQ | 1064 | 49% | -0.020 | -0.07 | +0.02 |
| smc_choch | US30 | 1043 | 47% | -0.040 | -0.02 | -0.06 |
| smc_choch | XAUUSD | 1090 | 49% | -0.025 | -0.04 | -0.01 |
| smc_displacement | NDQ | 421 | 49% | -0.012 | -0.06 | +0.03 |
| smc_displacement | US30 | 420 | 45% | -0.099 | -0.18 | -0.03 |
| smc_displacement | XAUUSD | 431 | 49% | +0.032 | +0.01 | +0.06 |
| smc_ifvg | NDQ | 1506 | 47% | -0.048 | -0.13 | +0.02 |
| smc_ifvg | US30 | 1676 | 44% | -0.136 | -0.11 | -0.16 |
| smc_ifvg | XAUUSD | 1528 | 49% | -0.019 | -0.04 | +0.01 |
| smc_liquidity_sweep | NDQ | 172 | 49% | +0.010 | +0.12 | -0.12 |
| smc_liquidity_sweep | US30 | 202 | 47% | -0.011 | +0.10 | -0.10 |
| smc_liquidity_sweep | XAUUSD | 113 | 54% | -0.025 | -0.10 | +0.06 |
| smc_mss | NDQ | 409 | 46% | -0.019 | -0.04 | +0.00 |
| smc_mss | US30 | 421 | 45% | -0.027 | -0.02 | -0.03 |
| smc_mss | XAUUSD | 332 | 47% | -0.075 | -0.09 | -0.06 |
| smc_order_block | NDQ | 879 | 44% | -0.137 | -0.20 | -0.08 |
| smc_order_block | US30 | 835 | 40% | -0.186 | -0.12 | -0.24 |
| smc_order_block | XAUUSD | 903 | 46% | -0.084 | -0.06 | -0.11 |
| smt_divergence | NDQ | 354 | 50% | +0.009 | +0.05 | -0.02 |
| smt_divergence | US30 | 391 | 43% | -0.079 | +0.00 | -0.16 |
| sr_rejection | NDQ | 2571 | 46% | -0.077 | -0.06 | -0.09 |
| sr_rejection | US30 | 2233 | 43% | -0.119 | -0.12 | -0.12 |
| sr_rejection | XAUUSD | 2859 | 44% | -0.138 | -0.14 | -0.13 |
| stoic_sbs | NDQ | 73 | 48% | -0.152 | -0.12 | -0.19 |
| stoic_sbs | US30 | 63 | 56% | +0.030 | -0.05 | +0.12 |
| stoic_sbs | XAUUSD | 75 | 59% | +0.118 | +0.20 | +0.04 |
| vwap | NDQ | 957 | 45% | -0.113 | -0.26 | +0.00 |
| vwap | US30 | 1129 | 46% | -0.044 | -0.07 | -0.02 |
| vwap | XAUUSD | 1095 | 49% | -0.020 | -0.06 | +0.03 |
| zone_confluence | NDQ | 640 | 45% | -0.090 | -0.19 | -0.00 |
| zone_confluence | US30 | 653 | 42% | -0.108 | -0.15 | -0.07 |
| zone_confluence | XAUUSD | 553 | 46% | -0.027 | +0.01 | -0.06 |

## 4 · Best cell per setup (≥30 trades, by t-stat)

| setup | variant | sym | tf | exit | trades | win | avg R | t | quarters positive |
|---|---|---|---|---|---|---|---|---|---|
| smc_displacement | disp_k=1.0 | XAUUSD | 15min | std | 67 | 66% | +0.279 | 2.5 | 4/4 |
| vwap | vol=dry | XAUUSD | 15min | std | 84 | 61% | +0.319 | 2.5 | 4/4 |
| rsi_pullback | default | XAUUSD | 15min | std | 79 | 63% | +0.255 | 2.4 | 3/4 |
| dtfx_wick_fib | vol=impulse | XAUUSD | 3min | scalp | 65 | 68% | +0.229 | 2.3 | 4/4 |
| dtfx_close_fib | vol=impulse | XAUUSD | 3min | scalp | 44 | 70% | +0.268 | 2.3 | 3/4 |
| ict_amd | manip=ny | NDQ | 3min | scalp | 39 | 67% | +0.165 | 2.1 | 4/4 |
| smc_ifvg | default | XAUUSD | 15min | std | 154 | 60% | +0.161 | 2.1 | 3/4 |
| ict_turtle_soup | level=session | US30 | 15min | std | 62 | 58% | +0.342 | 2.0 | 3/4 |
| dtfx_close_fib_brk | vol=impulse | US30 | 1min | std | 102 | 61% | +0.242 | 2.0 | 3/4 |
| dtfx_zone | default | NDQ | 30min | std | 55 | 64% | +0.162 | 2.0 | 3/4 |
| smc_choch | swing=2 | NDQ | 1h | std | 38 | 61% | +0.148 | 1.8 | 4/4 |
| ict_2022 | vol=impulse | XAUUSD | 1min | std | 34 | 56% | +0.500 | 1.6 | 4/4 |
| macd_cross | default | NDQ | 5min | std | 186 | 54% | +0.130 | 1.5 | 3/4 |
| dtfx_close_origin | vol=impulse | US30 | 1min | std | 102 | 56% | +0.212 | 1.5 | 4/4 |
| sr_rejection | default | NDQ | 30min | std | 124 | 54% | +0.131 | 1.4 | 3/4 |
| london_breakout | range_end=4 | US30 | 1min | scalp | 51 | 61% | +0.176 | 1.4 | 4/4 |
| stoic_sbs | default | XAUUSD | 3min | scalp | 43 | 60% | +0.179 | 1.4 | 4/4 |
| smt_divergence | confirm=reclaim | US30 | 1h | std | 39 | 59% | +0.232 | 1.3 | 4/4 |
| smc_mss | sweep_bars=10 | XAUUSD | 15min | std | 34 | 62% | +0.145 | 1.2 | 3/4 |
| smc_bos_retest | stop=level | XAUUSD | 15min | std | 131 | 54% | +0.093 | 1.1 | 3/4 |
| ict_silver_bullet | sb=am_pm | NDQ | 5min | scalp | 71 | 62% | +0.098 | 1.0 | 3/4 |
| zone_confluence | within=0 | US30 | 5min | scalp | 131 | 55% | +0.079 | 1.0 | 3/4 |
| smc_liquidity_sweep | default | US30 | 15min | std | 43 | 56% | +0.135 | 0.9 | 2/4 |
| ict_fvg_sweep | default | US30 | 5min | std | 71 | 46% | +0.093 | 0.6 | 3/4 |
| smc_order_block | default | US30 | 30min | std | 45 | 53% | +0.054 | 0.3 | 2/4 |
| ict_ote | default | NDQ | 5min | scalp | 226 | 50% | +0.006 | 0.1 | 1/4 |
| smc_breaker | default | US30 | 15min | std | 61 | 51% | -0.008 | -0.1 | 2/4 |
