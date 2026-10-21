# Trade-management replay — the bot's real trades, last 7 days

108 closed intraday trades across 7 book(s): c10_afternoon, ema21_rsi55, gold_breakout, h1_vol_trend, live, playbook, playbook_regime. Same entry minute, side and initial stop as the journal, replayed on OANDA 1-minute bid/ask with the Backtester's engine; only the management changes. R per trade before the CAD conversion. **actual** = what the journal recorded.

Read with care: one week is a small sample — a rule that wins here can lose next week. Use it to see *how* each rule changes outcomes (which trades it saves, which it cuts), then test the winner over years in the Backtester.

## All books

| rule | total R | avg R | vs actual | trades better | trades worse |
|---|---|---|---|---|---|
| **actual** (journal) | **-14.73** | -0.136 | — | — | — |
| replay with the real exit time (fidelity check) | +3.22 | +0.030 | +17.95 | 40 | 12 |
| stop only, hold to 15:50 / 4h | +9.94 | +0.092 | +24.68 | 32 | 25 |
| fixed 1R target | -9.62 | -0.089 | +5.11 | 34 | 20 |
| fixed 2R target | +4.80 | +0.044 | +19.53 | 40 | 17 |
| fixed 3R target | +7.35 | +0.068 | +22.08 | 36 | 21 |
| breakeven (+0.1R) at +1R | -9.53 | -0.088 | +5.21 | 28 | 30 |
| half at 1R, stop +0.1R, rest 2R | -7.73 | -0.072 | +7.00 | 33 | 18 |
| half at 1R, stop +0.1R, trail 1R from +2R (≈ bot) | -7.41 | -0.069 | +7.32 | 33 | 19 |
| trail 1R behind from +1R, no target | -12.46 | -0.115 | +2.27 | 32 | 26 |
| cut if not positive after 15 min, else 2R | +3.24 | +0.030 | +17.97 | 52 | 24 |
| cut if not positive after 30 min, else 2R | +3.52 | +0.033 | +18.25 | 49 | 20 |

Fidelity: replaying each trade with its real exit time gives +3.22R vs -14.73R recorded (+17.95R apart). The gap is the replay's fill model (minute opens, slippage) vs the real fills — compare the rules with each other and with this line, not to the decimal with the journal.

## c10_afternoon

| rule | total R | avg R | vs actual | trades better | trades worse |
|---|---|---|---|---|---|
| **actual** (journal) | **-1.00** | -1.000 | — | — | — |
| replay with the real exit time (fidelity check) | -0.91 | -0.911 | +0.09 | 1 | 0 |
| stop only, hold to 15:50 / 4h | -1.00 | -1.002 | -0.00 | 0 | 0 |
| fixed 1R target | -1.00 | -1.002 | -0.00 | 0 | 0 |
| fixed 2R target | -1.00 | -1.002 | -0.00 | 0 | 0 |
| fixed 3R target | -1.00 | -1.002 | -0.00 | 0 | 0 |
| breakeven (+0.1R) at +1R | -1.00 | -1.002 | -0.00 | 0 | 0 |
| half at 1R, stop +0.1R, rest 2R | -1.00 | -1.002 | -0.00 | 0 | 0 |
| half at 1R, stop +0.1R, trail 1R from +2R (≈ bot) | -1.00 | -1.002 | -0.00 | 0 | 0 |
| trail 1R behind from +1R, no target | -1.00 | -1.002 | -0.00 | 0 | 0 |
| cut if not positive after 15 min, else 2R | -1.00 | -1.002 | -0.00 | 0 | 0 |
| cut if not positive after 30 min, else 2R | -1.00 | -1.002 | -0.00 | 0 | 0 |

## ema21_rsi55

| rule | total R | avg R | vs actual | trades better | trades worse |
|---|---|---|---|---|---|
| **actual** (journal) | **-3.64** | -0.228 | — | — | — |
| replay with the real exit time (fidelity check) | -4.28 | -0.267 | -0.63 | 2 | 1 |
| stop only, hold to 15:50 / 4h | +1.36 | +0.085 | +5.01 | 10 | 4 |
| fixed 1R target | +0.16 | +0.010 | +3.80 | 10 | 4 |
| fixed 2R target | +1.16 | +0.072 | +4.80 | 10 | 4 |
| fixed 3R target | +1.36 | +0.085 | +5.01 | 10 | 4 |
| breakeven (+0.1R) at +1R | -0.75 | -0.047 | +2.90 | 10 | 4 |
| half at 1R, stop +0.1R, rest 2R | -0.30 | -0.019 | +3.35 | 10 | 4 |
| half at 1R, stop +0.1R, trail 1R from +2R (≈ bot) | -0.30 | -0.019 | +3.35 | 10 | 4 |
| trail 1R behind from +1R, no target | -0.73 | -0.045 | +2.92 | 10 | 4 |
| cut if not positive after 15 min, else 2R | -3.45 | -0.216 | +0.19 | 6 | 6 |
| cut if not positive after 30 min, else 2R | -4.42 | -0.276 | -0.77 | 9 | 5 |

## gold_breakout

| rule | total R | avg R | vs actual | trades better | trades worse |
|---|---|---|---|---|---|
| **actual** (journal) | **-1.88** | -0.627 | — | — | — |
| replay with the real exit time (fidelity check) | -0.76 | -0.252 | +1.13 | 2 | 0 |
| stop only, hold to 15:50 / 4h | -0.77 | -0.256 | +1.12 | 2 | 0 |
| fixed 1R target | -0.77 | -0.256 | +1.12 | 2 | 0 |
| fixed 2R target | -0.77 | -0.256 | +1.12 | 2 | 0 |
| fixed 3R target | -0.77 | -0.256 | +1.12 | 2 | 0 |
| breakeven (+0.1R) at +1R | -0.77 | -0.256 | +1.12 | 2 | 0 |
| half at 1R, stop +0.1R, rest 2R | -0.77 | -0.256 | +1.12 | 2 | 0 |
| half at 1R, stop +0.1R, trail 1R from +2R (≈ bot) | -0.77 | -0.256 | +1.12 | 2 | 0 |
| trail 1R behind from +1R, no target | -0.77 | -0.256 | +1.12 | 2 | 0 |
| cut if not positive after 15 min, else 2R | -0.47 | -0.156 | +1.41 | 3 | 0 |
| cut if not positive after 30 min, else 2R | -0.34 | -0.113 | +1.54 | 3 | 0 |

## h1_vol_trend

| rule | total R | avg R | vs actual | trades better | trades worse |
|---|---|---|---|---|---|
| **actual** (journal) | **-0.13** | -0.130 | — | — | — |
| replay with the real exit time (fidelity check) | +0.47 | +0.468 | +0.60 | 1 | 0 |
| stop only, hold to 15:50 / 4h | +0.47 | +0.468 | +0.60 | 1 | 0 |
| fixed 1R target | +0.47 | +0.468 | +0.60 | 1 | 0 |
| fixed 2R target | +0.47 | +0.468 | +0.60 | 1 | 0 |
| fixed 3R target | +0.47 | +0.468 | +0.60 | 1 | 0 |
| breakeven (+0.1R) at +1R | +0.47 | +0.468 | +0.60 | 1 | 0 |
| half at 1R, stop +0.1R, rest 2R | +0.47 | +0.468 | +0.60 | 1 | 0 |
| half at 1R, stop +0.1R, trail 1R from +2R (≈ bot) | +0.47 | +0.468 | +0.60 | 1 | 0 |
| trail 1R behind from +1R, no target | +0.47 | +0.468 | +0.60 | 1 | 0 |
| cut if not positive after 15 min, else 2R | +0.47 | +0.468 | +0.60 | 1 | 0 |
| cut if not positive after 30 min, else 2R | +0.47 | +0.468 | +0.60 | 1 | 0 |

## live

| rule | total R | avg R | vs actual | trades better | trades worse |
|---|---|---|---|---|---|
| **actual** (journal) | **+6.49** | +0.191 | — | — | — |
| replay with the real exit time (fidelity check) | +20.57 | +0.605 | +14.08 | 27 | 4 |
| stop only, hold to 15:50 / 4h | +24.99 | +0.735 | +18.50 | 9 | 12 |
| fixed 1R target | +2.76 | +0.081 | -3.74 | 10 | 9 |
| fixed 2R target | +13.48 | +0.397 | +6.99 | 14 | 7 |
| fixed 3R target | +18.52 | +0.545 | +12.02 | 12 | 9 |
| breakeven (+0.1R) at +1R | +8.94 | +0.263 | +2.45 | 6 | 15 |
| half at 1R, stop +0.1R, rest 2R | +4.41 | +0.130 | -2.08 | 10 | 9 |
| half at 1R, stop +0.1R, trail 1R from +2R (≈ bot) | +6.47 | +0.190 | -0.03 | 10 | 10 |
| trail 1R behind from +1R, no target | +2.42 | +0.071 | -4.08 | 6 | 14 |
| cut if not positive after 15 min, else 2R | +15.88 | +0.467 | +9.38 | 20 | 7 |
| cut if not positive after 30 min, else 2R | +16.11 | +0.474 | +9.62 | 17 | 6 |

## playbook

| rule | total R | avg R | vs actual | trades better | trades worse |
|---|---|---|---|---|---|
| **actual** (journal) | **-12.81** | -0.320 | — | — | — |
| replay with the real exit time (fidelity check) | -10.75 | -0.269 | +2.06 | 6 | 6 |
| stop only, hold to 15:50 / 4h | -13.69 | -0.342 | -0.88 | 6 | 7 |
| fixed 1R target | -8.61 | -0.215 | +4.20 | 8 | 5 |
| fixed 2R target | -8.74 | -0.218 | +4.08 | 8 | 5 |
| fixed 3R target | -10.27 | -0.257 | +2.55 | 7 | 6 |
| breakeven (+0.1R) at +1R | -13.83 | -0.346 | -1.01 | 6 | 8 |
| half at 1R, stop +0.1R, rest 2R | -8.97 | -0.224 | +3.84 | 7 | 4 |
| half at 1R, stop +0.1R, trail 1R from +2R (≈ bot) | -9.94 | -0.248 | +2.88 | 7 | 4 |
| trail 1R behind from +1R, no target | -10.83 | -0.271 | +1.98 | 9 | 6 |
| cut if not positive after 15 min, else 2R | -7.06 | -0.177 | +5.75 | 16 | 8 |
| cut if not positive after 30 min, else 2R | -6.60 | -0.165 | +6.21 | 14 | 7 |

## playbook_regime

| rule | total R | avg R | vs actual | trades better | trades worse |
|---|---|---|---|---|---|
| **actual** (journal) | **-1.75** | -0.135 | — | — | — |
| replay with the real exit time (fidelity check) | -1.13 | -0.087 | +0.63 | 1 | 1 |
| stop only, hold to 15:50 / 4h | -1.42 | -0.109 | +0.33 | 4 | 2 |
| fixed 1R target | -2.62 | -0.201 | -0.86 | 3 | 2 |
| fixed 2R target | +0.20 | +0.015 | +1.95 | 5 | 1 |
| fixed 3R target | -0.96 | -0.074 | +0.79 | 4 | 2 |
| breakeven (+0.1R) at +1R | -2.59 | -0.199 | -0.84 | 3 | 3 |
| half at 1R, stop +0.1R, rest 2R | -1.57 | -0.121 | +0.18 | 3 | 1 |
| half at 1R, stop +0.1R, trail 1R from +2R (≈ bot) | -2.34 | -0.180 | -0.59 | 3 | 1 |
| trail 1R behind from +1R, no target | -2.02 | -0.155 | -0.27 | 4 | 2 |
| cut if not positive after 15 min, else 2R | -1.12 | -0.086 | +0.63 | 6 | 3 |
| cut if not positive after 30 min, else 2R | -0.70 | -0.054 | +1.05 | 5 | 2 |

## By setup (total R)

| setup | trades | actual | actual_exit | stop_only | target_1r | target_2r | target_3r | be1 | part1_2r | bot_approx | trail1 | cut15 | cut30 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astra_h1_vol_trend | 1 | -0.13 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 |
| c10_afternoon | 1 | -1.00 | -0.91 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| dtfx_close_fib | 9 | -1.76 | -1.71 | -1.65 | -2.18 | -1.65 | -1.65 | -1.65 | -1.92 | -1.92 | -2.80 | -1.48 | -3.44 |
| dtfx_wick_fib | 12 | -1.44 | -0.36 | -2.22 | +3.09 | +0.67 | -2.22 | -2.27 | +2.32 | +1.60 | +0.74 | +0.16 | -0.28 |
| ema21_rsi55 | 16 | -3.64 | -4.27 | +1.36 | +0.16 | +1.16 | +1.36 | -0.75 | -0.30 | -0.30 | -0.72 | -3.45 | -4.42 |
| gold_breakout | 3 | -1.88 | -0.76 | -0.77 | -0.77 | -0.77 | -0.77 | -0.77 | -0.77 | -0.77 | -0.77 | -0.47 | -0.34 |
| ict_amd | 4 | +1.03 | +2.94 | +3.06 | -0.03 | +1.97 | +3.97 | +3.06 | +0.97 | +1.04 | +2.10 | -2.10 | +1.97 |
| ict_ote | 8 | -1.63 | -0.48 | -1.63 | -1.57 | +0.20 | -1.81 | -0.53 | -1.64 | -1.79 | -3.14 | +1.66 | +1.48 |
| ict_turtle_soup | 3 | +0.66 | +0.74 | +0.15 | +0.99 | +0.66 | +0.15 | +0.58 | +1.04 | +0.71 | +1.06 | +1.05 | +1.45 |
| macd_cross | 4 | -2.46 | -2.86 | -2.19 | -2.00 | -2.19 | -2.19 | -2.91 | -2.46 | -2.46 | -2.86 | -0.23 | -1.19 |
| smc_bos_retest | 3 | -1.48 | -1.90 | -0.88 | -1.02 | -0.02 | -0.88 | -1.92 | -1.47 | -1.47 | -1.75 | +0.29 | +0.73 |
| smc_displacement | 5 | -5.00 | -5.04 | -5.04 | -5.04 | -5.04 | -5.04 | -5.04 | -5.04 | -5.04 | -5.04 | -5.04 | -4.53 |
| smc_ifvg | 2 | +1.67 | +2.78 | +14.17 | +2.00 | +0.99 | +1.99 | +0.15 | +1.08 | +1.08 | +0.13 | -1.59 | +1.60 |
| smc_mss | 9 | -0.11 | +0.33 | -2.31 | -1.02 | +1.08 | +0.66 | -2.26 | +0.02 | -0.73 | -0.28 | +1.39 | +2.02 |
| sr_rejection | 28 | +2.46 | +14.25 | +8.43 | -1.69 | +8.27 | +14.32 | +5.30 | +0.95 | +3.16 | +1.41 | +13.57 | +9.01 |

## Every trade

| book | opened (NY) | symbol | side | strategy | actual | actual_exit | stop_only | target_1r | target_2r | target_3r | be1 | part1_2r | bot_approx | trail1 | cut15 | cut30 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| live | Wed 10-14 02:10 | US30 | LONG | sr_rejection:5m@v1 | +0.61 | +0.70 | +3.95 | +1.00 | +2.00 | +3.00 | +0.08 | +0.54 | +0.54 | +0.69 | +2.00 | +2.00 |
| playbook | Wed 10-14 02:15 | US30 | LONG | ict_amd:5m@pb-us30-013f | +1.52 | +2.48 | +2.54 | +1.00 | +2.00 | +3.00 | +2.54 | +1.50 | +1.53 | +2.06 | -0.32 | +2.00 |
| playbook_regime | Wed 10-14 02:15 | US30 | LONG | ict_amd:5m@pb-us30-013f | +1.51 | +2.48 | +2.54 | +1.00 | +2.00 | +3.00 | +2.54 | +1.50 | +1.53 | +2.06 | -0.32 | +2.00 |
| live | Wed 10-14 03:55 | US30 | LONG | sr_rejection:5m@v1 | +2.49 | +5.12 | +1.78 | +1.01 | +2.00 | +3.00 | +1.78 | +1.50 | +1.60 | +2.20 | +2.00 | +2.00 |
| ema21_rsi55 | Wed 10-14 07:45 | US30 | LONG | ema21_rsi55 | +0.10 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -0.18 | -1.02 |
| h1_vol_trend | Wed 10-14 09:00 | XAUUSD | SHORT | astra_h1_vol_trend | -0.13 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 | +0.47 |
| playbook | Wed 10-14 09:12 | XAUUSD | SHORT | dtfx_close_fib:3m@pb-xau-4a8c | +0.24 | +0.24 | +0.24 | +0.24 | +0.24 | +0.24 | +0.24 | +0.24 | +0.24 | +0.24 | -0.04 | -0.65 |
| playbook_regime | Wed 10-14 09:12 | XAUUSD | SHORT | dtfx_close_fib:3m@pb-xau-4a8c | +0.24 | +0.24 | +0.24 | +0.24 | +0.24 | +0.24 | +0.24 | +0.24 | +0.24 | +0.24 | -0.04 | -0.65 |
| playbook | Wed 10-14 09:18 | XAUUSD | SHORT | dtfx_wick_fib:3m@pb-xau-4a8c | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| playbook_regime | Wed 10-14 09:18 | XAUUSD | SHORT | dtfx_wick_fib:3m@pb-xau-4a8c | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| live | Wed 10-14 14:30 | XAUUSD | SHORT | ict_ote:15m@v1 | -0.60 | -0.54 | -0.56 | -0.56 | -0.56 | -0.56 | -0.56 | -0.56 | -0.56 | -0.56 | -0.56 | -0.17 |
| playbook | Wed 10-14 22:30 | NDQ | SHORT | dtfx_wick_fib:15m@pb-ndq-b988-trend | +0.32 | +0.12 | +0.12 | +0.12 | +0.12 | +0.12 | +0.12 | +0.12 | +0.12 | +0.12 | +0.12 | +0.12 |
| live | Thu 10-15 02:15 | NDQ | SHORT | ict_ote:15m@v1 | +1.01 | +0.89 | +0.77 | +1.00 | +0.77 | +0.77 | +0.77 | +0.89 | +0.89 | +0.74 | +0.77 | +0.77 |
| ema21_rsi55 | Thu 10-15 03:15 | XAUUSD | LONG | ema21_rsi55 | +0.34 | +0.69 | +0.69 | +0.69 | +0.69 | +0.69 | +0.69 | +0.69 | +0.69 | +0.69 | -0.00 | +0.69 |
| live | Thu 10-15 04:10 | NDQ | SHORT | sr_rejection:5m@v1 | -1.01 | -0.90 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -0.28 | -1.01 |
| ema21_rsi55 | Thu 10-15 07:45 | US30 | LONG | ema21_rsi55 | -0.41 | -0.40 | +2.21 | +1.00 | +2.00 | +2.21 | +0.10 | +0.55 | +0.55 | +0.12 | -0.40 | -0.22 |
| playbook | Thu 10-15 09:00 | NDQ | SHORT | dtfx_wick_fib:15m@pb-ndq-b988-trend | -1.00 | -1.00 | -1.00 | +1.00 | -1.00 | -1.00 | +0.10 | +0.55 | +0.55 | +0.04 | -0.18 | -1.00 |
| gold_breakout | Thu 10-15 09:16 | XAUUSD | LONG | gold_breakout | -0.35 | -0.38 | -0.39 | -0.39 | -0.39 | -0.39 | -0.39 | -0.39 | -0.39 | -0.39 | -0.18 | -0.17 |
| live | Thu 10-15 10:15 | NDQ | SHORT | sr_rejection:5m@v1 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.28 | -1.00 |
| playbook | Thu 10-15 20:00 | US30 | LONG | dtfx_close_fib:15m@pb-us30-b988-trend | +1.50 | +1.53 | +1.53 | +1.00 | +1.53 | +1.53 | +1.53 | +1.27 | +1.27 | +0.38 | +1.53 | +1.53 |
| live | Thu 10-15 20:20 | NDQ | SHORT | smc_ifvg:5m@v1 | +0.33 | +0.52 | -1.01 | +1.00 | -1.01 | -1.01 | +0.09 | +0.55 | +0.55 | +0.09 | -1.01 | -0.40 |
| live | Thu 10-15 21:00 | NDQ | SHORT | sr_rejection:5m@v1 | -1.01 | -0.37 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 |
| gold_breakout | Fri 10-16 00:01 | XAUUSD | LONG | gold_breakout | -0.53 | +0.03 | +0.03 | +0.03 | +0.03 | +0.03 | +0.03 | +0.03 | +0.03 | +0.03 | -0.17 | -0.13 |
| live | Fri 10-16 02:15 | US30 | LONG | ict_ote:15m@v1 | +1.56 | +2.27 | +3.18 | +1.00 | +2.00 | +3.00 | +3.18 | +1.50 | +1.35 | +0.59 | +2.00 | +2.00 |
| ema21_rsi55 | Fri 10-16 02:30 | XAUUSD | LONG | ema21_rsi55 | +0.16 | +0.17 | +0.38 | +0.38 | +0.38 | +0.38 | +0.38 | +0.38 | +0.38 | +0.38 | +0.38 | +0.38 |
| playbook | Fri 10-16 04:15 | US30 | LONG | dtfx_close_fib:15m@pb-us30-b988-trend | -1.00 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 |
| live | Fri 10-16 09:00 | NDQ | SHORT | smc_ifvg:5m@v1 | +1.34 | +2.26 | +15.17 | +1.00 | +2.00 | +3.00 | +0.06 | +0.53 | +0.53 | +0.04 | -0.58 | +2.00 |
| playbook | Fri 10-16 09:33 | XAUUSD | SHORT | smc_displacement:3m@pb-xau-d | -1.00 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 |
| playbook | Fri 10-16 10:30 | NDQ | SHORT | sr_rejection:30m@pb-ndq-d | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| playbook_regime | Fri 10-16 10:30 | US30 | LONG | dtfx_close_fib:15m@pb-us30-b988-trend | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.25 | -1.00 |
| live | Fri 10-16 10:45 | US30 | LONG | ict_ote:15m@v1 | -1.00 | -0.85 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| playbook | Fri 10-16 11:00 | US30 | LONG | sr_rejection:30m@pb-us30-d-trend | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.28 | -1.00 |
| playbook | Sun 10-18 20:00 | US30 | LONG | sr_rejection:30m@pb-us30-d-trend | -1.00 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -0.47 | -1.01 |
| playbook_regime | Sun 10-18 20:00 | US30 | LONG | sr_rejection:30m@pb-us30-d-trend | -1.00 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -0.47 | -1.01 |
| playbook | Sun 10-18 21:06 | XAUUSD | SHORT | dtfx_wick_fib:3m@pb-xau-4a8c | -1.00 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -0.64 |
| live | Sun 10-18 21:40 | US30 | LONG | sr_rejection:5m@v1 | +3.84 | +7.40 | +7.16 | +1.00 | +2.00 | +3.00 | +7.16 | +1.50 | +3.12 | +5.24 | +2.00 | +2.00 |
| playbook | Mon 10-19 02:15 | XAUUSD | SHORT | smc_mss:3m@pb-xau-d | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| playbook_regime | Mon 10-19 02:15 | XAUUSD | SHORT | smc_mss:3m@pb-xau-3c77-scalp | +0.08 | +0.09 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| playbook | Mon 10-19 02:24 | XAUUSD | SHORT | smc_displacement:3m@pb-xau-d | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.49 |
| ema21_rsi55 | Mon 10-19 03:00 | XAUUSD | LONG | ema21_rsi55 | -0.54 | -0.53 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.03 | -1.00 |
| gold_breakout | Mon 10-19 03:01 | XAUUSD | LONG | gold_breakout | -1.00 | -0.41 | -0.41 | -0.41 | -0.41 | -0.41 | -0.41 | -0.41 | -0.41 | -0.41 | -0.13 | -0.04 |
| playbook | Mon 10-19 03:42 | XAUUSD | SHORT | smc_mss:3m@pb-xau-d | +0.94 | +1.24 | +1.29 | +1.00 | +2.00 | +1.29 | +1.29 | +1.50 | +1.05 | +1.11 | +2.00 | +2.00 |
| playbook_regime | Mon 10-19 03:42 | XAUUSD | SHORT | smc_mss:3m@pb-xau-3c77-scalp | +0.77 | +0.81 | +1.29 | +1.00 | +2.00 | +1.29 | +1.29 | +1.50 | +1.05 | +1.11 | +2.00 | +2.00 |
| playbook | Mon 10-19 03:45 | XAUUSD | SHORT | ict_turtle_soup:5m@pb-xau-285e | +1.07 | +1.64 | +1.49 | +1.00 | +2.00 | +1.49 | +1.49 | +1.50 | +1.17 | +1.34 | +2.00 | +2.00 |
| playbook | Mon 10-19 03:45 | NDQ | SHORT | dtfx_wick_fib:15m@pb-ndq-b988-trend | -1.00 | +0.85 | +0.85 | +1.00 | +0.85 | +0.85 | +0.10 | +0.55 | +0.55 | +0.38 | +0.85 | +0.85 |
| ema21_rsi55 | Mon 10-19 04:00 | XAUUSD | SHORT | ema21_rsi55 | -0.12 | -0.11 | +0.50 | +0.50 | +0.50 | +0.50 | +0.50 | +0.50 | +0.50 | +0.50 | -0.29 | -0.22 |
| live | Mon 10-19 09:10 | US30 | LONG | sr_rejection:5m@v1 | -1.03 | -0.61 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -0.61 | -1.01 |
| playbook | Mon 10-19 09:40 | XAUUSD | SHORT | smc_bos_retest:5m@pb-xau-00dd | +0.52 | +0.12 | +1.14 | +1.00 | +2.00 | +1.14 | +0.09 | +0.55 | +0.55 | +0.27 | +2.00 | +2.00 |
| live | Mon 10-19 09:55 | US30 | LONG | sr_rejection:5m@v1 | +0.98 | +2.27 | +3.26 | +1.00 | +2.00 | +3.00 | +3.26 | +1.50 | +2.09 | +0.01 | +2.00 | +2.00 |
| playbook | Mon 10-19 10:03 | XAUUSD | SHORT | dtfx_close_fib:3m@pb-xau-4a8c | +0.16 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 |
| playbook_regime | Mon 10-19 10:03 | XAUUSD | SHORT | dtfx_close_fib:3m@pb-xau-4a8c-scalp | +0.10 | +0.11 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 | +0.17 |
| ema21_rsi55 | Mon 10-19 10:15 | US30 | LONG | ema21_rsi55 | -0.55 | -0.55 | +0.09 | +0.09 | +0.09 | +0.09 | +0.09 | +0.09 | +0.09 | +0.09 | -0.20 | -0.55 |
| ema21_rsi55 | Mon 10-19 10:45 | US30 | SHORT | ema21_rsi55 | -0.23 | -0.22 | -0.58 | -0.58 | -0.58 | -0.58 | -0.58 | -0.58 | -0.58 | -0.58 | -0.22 | -0.48 |
| playbook | Mon 10-19 10:54 | XAUUSD | SHORT | dtfx_wick_fib:3m@pb-xau-4a8c | +0.48 | +0.07 | -0.52 | +1.00 | -0.52 | -0.52 | +0.09 | +0.54 | +0.54 | +0.28 | -0.21 | -0.52 |
| live | Mon 10-19 14:15 | US30 | LONG | sr_rejection:15m@v1 | -0.47 | -0.42 | -0.55 | -0.55 | -0.55 | -0.55 | -0.55 | -0.55 | -0.55 | -0.55 | -0.08 | -0.18 |
| live | Mon 10-19 14:45 | NDQ | SHORT | ict_ote:5m@v1 | -1.07 | -0.74 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.22 | -1.00 |
| live | Mon 10-19 20:00 | US30 | LONG | sr_rejection:5m@v1 | +0.56 | +0.64 | -1.03 | +1.00 | -1.03 | -1.03 | +0.08 | +0.54 | +0.54 | +0.19 | -1.03 | -1.03 |
| live | Mon 10-19 20:05 | NDQ | SHORT | sr_rejection:5m@v1 | +0.93 | +1.80 | -1.01 | +1.00 | +2.00 | +3.00 | +0.09 | +1.50 | +1.59 | +2.19 | +2.00 | +2.00 |
| playbook | Mon 10-19 20:05 | NDQ | SHORT | dtfx_wick_fib:5m@pb-ndq-4a8c-scalp | +1.01 | +1.01 | +0.55 | +1.00 | +2.00 | +0.55 | +0.09 | +1.50 | +1.14 | +1.28 | +2.00 | +2.00 |
| playbook_regime | Mon 10-19 20:05 | NDQ | SHORT | dtfx_wick_fib:5m@pb-ndq-4a8c-scalp | +1.01 | +1.01 | +0.55 | +1.00 | +2.00 | +0.55 | +0.09 | +1.50 | +1.14 | +1.28 | +2.00 | +2.00 |
| playbook | Mon 10-19 20:27 | XAUUSD | SHORT | smc_displacement:3m@pb-xau-d | -1.00 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 |
| live | Mon 10-19 21:05 | NDQ | SHORT | sr_rejection:5m@v1 | -1.00 | -0.65 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 |
| playbook | Mon 10-19 21:15 | XAUUSD | SHORT | smc_bos_retest:5m@pb-xau-392f | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.26 |
| live | Mon 10-19 21:40 | US30 | LONG | sr_rejection:5m@v1 | +0.61 | +0.64 | -1.03 | +1.00 | +2.00 | +3.00 | +0.07 | +1.50 | +1.09 | +1.17 | +2.00 | +2.00 |
| playbook | Mon 10-19 22:15 | NDQ | SHORT | dtfx_wick_fib:15m@pb-ndq-b988 | +1.00 | +1.08 | +1.08 | +1.00 | +1.08 | +1.08 | +1.08 | +1.04 | +1.04 | +1.08 | -0.23 | -0.26 |
| playbook | Tue 10-20 02:18 | US30 | LONG | ict_amd:3m@pb-us30-013f | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| ema21_rsi55 | Tue 10-20 03:15 | XAUUSD | SHORT | ema21_rsi55 | +0.21 | +0.27 | +0.27 | +0.27 | +0.27 | +0.27 | +0.27 | +0.27 | +0.27 | +0.27 | -0.13 | +0.27 |
| live | Tue 10-20 03:20 | US30 | LONG | sr_rejection:5m@v1 | -1.02 | -0.51 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 |
| playbook_regime | Tue 10-20 03:25 | NDQ | SHORT | macd_cross:5m@pb-ndq-d | +0.54 | +0.14 | +0.81 | +1.00 | +0.81 | +0.81 | +0.10 | +0.55 | +0.55 | +0.14 | +0.81 | +0.81 |
| playbook | Tue 10-20 03:36 | XAUUSD | SHORT | smc_mss:3m@pb-xau-d | +0.69 | +0.37 | +0.10 | +1.00 | +0.10 | +0.10 | +0.09 | +0.55 | +0.55 | +0.24 | +0.10 | +0.10 |
| live | Tue 10-20 04:05 | US30 | LONG | sr_rejection:5m@v1 | +0.71 | +0.77 | -1.03 | +1.00 | +2.00 | +3.00 | +0.08 | +1.50 | +1.24 | +1.47 | +2.00 | +2.00 |
| live | Tue 10-20 04:25 | US30 | LONG | sr_rejection:5m@v1 | +0.46 | +0.07 | -1.01 | +1.00 | +2.00 | -1.01 | +0.09 | +0.54 | +0.54 | +0.03 | +2.00 | +2.00 |
| ema21_rsi55 | Tue 10-20 05:15 | US30 | SHORT | ema21_rsi55 | -0.54 | -0.54 | +0.50 | +0.50 | +0.50 | +0.50 | +0.50 | +0.50 | +0.50 | +0.50 | -0.54 | -0.35 |
| live | Tue 10-20 08:30 | XAUUSD | SHORT | ict_ote:15m@v1 | -1.00 | -0.87 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.32 | -0.11 |
| playbook | Tue 10-20 08:30 | XAUUSD | SHORT | ict_turtle_soup:5m@pb-xau-285e | -1.00 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -0.61 | -0.21 |
| playbook | Tue 10-20 09:40 | NDQ | SHORT | macd_cross:5m@pb-ndq-d | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.20 | -1.00 |
| live | Tue 10-20 09:45 | US30 | LONG | sr_rejection:5m@v1 | +1.52 | +1.80 | +3.77 | +1.00 | +2.00 | +3.00 | +3.77 | +1.50 | +1.34 | +0.79 | +2.00 | +2.00 |
| live | Tue 10-20 09:55 | NDQ | SHORT | ict_ote:5m@v1 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| playbook | Tue 10-20 10:03 | XAUUSD | SHORT | smc_mss:3m@pb-xau-d | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| live | Tue 10-20 15:00 | NDQ | SHORT | sr_rejection:5m@v1 | +1.17 | +1.31 | +1.06 | +1.00 | +2.00 | +1.06 | +1.06 | +1.50 | +1.06 | +1.12 | +2.00 | +2.00 |
| playbook | Tue 10-20 20:00 | XAUUSD | SHORT | smc_bos_retest:5m@pb-xau-392f | -1.00 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -0.70 | -1.01 |
| live | Tue 10-20 20:40 | US30 | LONG | sr_rejection:5m@v1 | -1.02 | -0.62 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 |
| playbook | Tue 10-20 21:15 | XAUUSD | SHORT | smc_displacement:3m@pb-xau-d | -1.00 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 |
| playbook_regime | Tue 10-20 21:15 | XAUUSD | SHORT | smc_displacement:3m@pb-xau-d | -1.00 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 |
| live | Tue 10-20 22:20 | US30 | LONG | sr_rejection:5m@v1 | +0.42 | +0.33 | +4.84 | +1.00 | +2.00 | +3.00 | +0.05 | +0.53 | +0.53 | +0.02 | +2.00 | +2.00 |
| live | Tue 10-20 23:30 | US30 | LONG | sr_rejection:5m@v1 | -1.02 | -0.91 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -0.46 | -1.02 |
| live | Wed 10-21 02:35 | US30 | LONG | sr_rejection:5m@v1 | -1.03 | -0.93 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -0.40 | -1.02 |
| playbook | Wed 10-21 02:36 | US30 | LONG | ict_amd:3m@pb-us30-013f | -1.00 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -1.02 | -0.46 | -1.02 |
| live | Wed 10-21 02:40 | NDQ | SHORT | sr_rejection:5m@v1 | +0.18 | +0.30 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -0.64 |
| playbook | Wed 10-21 03:06 | XAUUSD | SHORT | dtfx_wick_fib:3m@pb-xau-2ca4 | -1.00 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 |
| playbook_regime | Wed 10-21 03:06 | XAUUSD | SHORT | dtfx_close_fib:3m@pb-xau-4a8c-scalp | -1.00 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 |
| live | Wed 10-21 03:30 | XAUUSD | SHORT | ict_ote:15m@v1 | +0.48 | +0.36 | -1.01 | +1.00 | +2.00 | -1.01 | +0.09 | +0.55 | +0.55 | +0.10 | +2.00 | +2.00 |
| ema21_rsi55 | Wed 10-21 03:30 | XAUUSD | LONG | ema21_rsi55 | -0.28 | -0.28 | +0.26 | +0.26 | +0.26 | +0.26 | +0.26 | +0.26 | +0.26 | +0.26 | -0.23 | -0.05 |
| playbook | Wed 10-21 03:45 | NDQ | SHORT | dtfx_wick_fib:15m@pb-ndq-b988 | +0.76 | +0.52 | +0.17 | +1.00 | +0.17 | +0.17 | +0.10 | +0.55 | +0.55 | +0.31 | -0.16 | +0.17 |
| playbook | Wed 10-21 04:18 | XAUUSD | SHORT | smc_mss:3m@pb-xau-d | -1.00 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -1.01 | -0.69 | -0.69 |
| ema21_rsi55 | Wed 10-21 05:15 | XAUUSD | LONG | ema21_rsi55 | -0.39 | -0.38 | +0.64 | +0.64 | +0.64 | +0.64 | +0.64 | +0.64 | +0.64 | +0.64 | -0.13 | -0.16 |
| ema21_rsi55 | Wed 10-21 06:00 | US30 | SHORT | ema21_rsi55 | -0.28 | -0.28 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| playbook | Wed 10-21 09:45 | NDQ | SHORT | macd_cross:5m@pb-ndq-d | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.71 | -1.00 |
| playbook | Wed 10-21 10:00 | XAUUSD | SHORT | smc_mss:3m@pb-xau-d | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.38 |
| playbook_regime | Wed 10-21 10:00 | US30 | LONG | dtfx_close_fib:15m@pb-us30-b988-trend | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| playbook | Wed 10-21 10:10 | NDQ | SHORT | macd_cross:5m@pb-ndq-d | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.13 | -0.00 |
| ema21_rsi55 | Wed 10-21 10:30 | XAUUSD | LONG | ema21_rsi55 | -0.26 | -0.24 | +0.30 | +0.30 | +0.30 | +0.30 | +0.30 | +0.30 | +0.30 | +0.30 | -0.24 | -0.17 |
| live | Wed 10-21 11:05 | US30 | LONG | sr_rejection:5m@v1 | +1.57 | +2.04 | +2.43 | +1.00 | +2.00 | +3.00 | +2.43 | +1.50 | +2.57 | +0.98 | +2.00 | +2.00 |
| c10_afternoon | Wed 10-21 13:00 | NDQ | LONG | c10_afternoon | -1.00 | -0.91 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 |
| playbook | Wed 10-21 14:48 | XAUUSD | SHORT | smc_mss:3m@pb-xau-d | +1.41 | +1.84 | +0.03 | +1.00 | +2.00 | +3.00 | +0.09 | +1.50 | +1.64 | +2.28 | +2.00 | +2.00 |
| playbook | Wed 10-21 14:50 | XAUUSD | SHORT | ict_turtle_soup:5m@pb-xau-285e | +0.59 | +0.10 | -0.34 | +1.00 | -0.34 | -0.34 | +0.10 | +0.55 | +0.55 | +0.73 | -0.34 | -0.34 |
| ema21_rsi55 | Wed 10-21 15:00 | XAUUSD | SHORT | ema21_rsi55 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -1.00 | -0.22 | -0.66 |
| ema21_rsi55 | Wed 10-21 15:30 | US30 | LONG | ema21_rsi55 | +0.14 | +0.13 | +0.13 | +0.13 | +0.13 | +0.13 | +0.13 | +0.13 | +0.13 | +0.13 | -0.02 | +0.13 |
