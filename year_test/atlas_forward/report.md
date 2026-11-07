# Trade atlas: what every book has actually done (forward)

511 closed trades in 9 books, 2026-10-05 → 2026-11-06 (pooled across books, the same signal counted once: 418). Pips = net P&L ÷ ($ per pip × all units traded), as the dashboard. Bias = the bias at entry: the no-bias books record what the rule *would* have said, so they are where neutral and counter-bias trades show up; rule-based books (C10, gold breakout, EMA/RSI, …) have no bias (n/a).

**Samples are small.** A slice needs about 100 trades before its average means much; most here have far fewer. Read this as what happened, and use the history atlas for what tends to happen.

## 1. Books

| book | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|
| h1_vol_trend | 4 | 50% | **+0.75** | — | +1,000 | +554 | -54 |
| c10_afternoon | 6 | 67% | **+0.41** | — | +136 | +105 | -142 |
| playbook_allhours | 44 | 55% | **+0.28** | — | +1,224 | +135 | -101 |
| gold_breakout | 13 | 46% | **+0.18** | — | +928 | +486 | -284 |
| playbook_nobias | 86 | 49% | **+0.08** | — | +206 | +120 | -110 |
| practice | 127 | 50% | **-0.02** | -0.20 to +0.07 | -1,421 | +48 | -71 |
| ema21_rsi55 | 48 | 29% | **-0.04** | -0.27 to +0.33 | -61 | +185 | -78 |
| playbook_nobias_allhours | 51 | 49% | **-0.04** | — | -594 | +94 | -113 |
| playbook | 132 | 44% | **-0.09** | -0.31 to +0.30 | -828 | +102 | -91 |

## 2. Bias at entry (pooled, each signal once)

| bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|
| n/a | 71 | 37% | **+0.08** | -0.24 to +0.47 | +2,003 | +271 | -112 |
| counter | 33 | 42% | **-0.02** | — | -222 | +131 | -108 |
| aligned | 289 | 48% | **-0.03** | -0.20 to +0.12 | -1,077 | +81 | -83 |
| neutral | 25 | 32% | **-0.43** | — | -1,526 | +39 | -108 |

### Setup × bias: avg R (trades)

| setup | aligned | neutral | counter | n/a | all |
|---|---|---|---|---|---|
| smc_choch | [+1.16 (1)] |  |  |  | [+1.16 (1)] |
| dtfx_close_fib_brk | [+0.92 (1)] |  |  |  | [+0.92 (1)] |
| astra_h1_vol_trend |  |  |  | [+0.75 (4)] | [+0.75 (4)] |
| ict_silver_bullet | [+0.54 (3)] |  |  |  | [+0.54 (3)] |
| c10_afternoon |  |  |  | [+0.41 (6)] | [+0.41 (6)] |
| ict_amd | [+0.48 (9)] |  | [+0.08 (3)] |  | +0.38 (12) |
| dtfx_close_fib | +0.49 (18) | [-0.20 (5)] | [+0.19 (4)] |  | +0.32 (27) |
| trend_breakout | [+0.30 (5)] |  |  |  | [+0.30 (5)] |
| gold_breakout |  |  |  | +0.18 (13) | +0.18 (13) |
| sr_rejection | -0.01 (69) | [+0.52 (2)] | [-1.00 (1)] |  | -0.01 (72) |
| smc_mss | +0.28 (25) | [-0.71 (8)] | [-1.00 (2)] |  | -0.02 (35) |
| smc_bos_retest | -0.10 (20) |  | [+1.45 (1)] |  | -0.03 (21) |
| ema21_rsi55 |  |  |  | -0.04 (48) | -0.04 (48) |
| ict_ote | -0.16 (36) |  | [+1.07 (3)] |  | -0.07 (39) |
| ict_turtle_soup | +0.10 (15) | [-0.76 (5)] | [+0.35 (2)] |  | -0.07 (22) |
| dtfx_close_origin | [-0.16 (8)] |  | -0.03 (10) |  | -0.09 (18) |
| zone_confluence | [-0.09 (2)] |  |  |  | [-0.09 (2)] |
| smc_ifvg | -0.21 (28) |  |  |  | -0.21 (28) |
| dtfx_wick_fib | -0.18 (29) | [-0.25 (5)] | [-0.57 (3)] |  | -0.22 (37) |
| ict_2022 | [-0.44 (8)] |  |  |  | [-0.44 (8)] |
| smc_displacement | [-1.00 (5)] |  | [+1.00 (1)] |  | [-0.67 (6)] |
| macd_cross | [-0.59 (6)] |  | [-1.00 (3)] |  | [-0.73 (9)] |
| ict_fvg_sweep | [-1.02 (1)] |  |  |  | [-1.02 (1)] |

### Per book × bias

| book | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|
| practice | n/a | 5 | 80% | **+0.78** | — | +216 | +115 | -243 |
| h1_vol_trend | n/a | 4 | 50% | **+0.75** | — | +1,000 | +554 | -54 |
| playbook_nobias | aligned | 40 | 62% | **+0.41** | — | +1,597 | +123 | -98 |
| c10_afternoon | n/a | 6 | 67% | **+0.41** | — | +136 | +105 | -142 |
| playbook_allhours | aligned | 44 | 55% | **+0.28** | — | +1,224 | +135 | -101 |
| gold_breakout | n/a | 13 | 46% | **+0.18** | — | +928 | +486 | -284 |
| playbook_nobias_allhours | aligned | 18 | 56% | **+0.10** | — | +217 | +142 | -151 |
| playbook_nobias | counter | 27 | 44% | **-0.02** | — | -102 | +143 | -121 |
| ema21_rsi55 | n/a | 48 | 29% | **-0.04** | -0.27 to +0.33 | -61 | +185 | -78 |
| practice | aligned | 122 | 49% | **-0.05** | -0.22 to +0.01 | -1,637 | +44 | -69 |
| playbook | aligned | 132 | 44% | **-0.09** | -0.31 to +0.30 | -828 | +102 | -91 |
| playbook_nobias_allhours | counter | 20 | 40% | **-0.10** | — | -443 | +94 | -100 |
| playbook_nobias_allhours | neutral | 13 | 54% | **-0.17** | — | -368 | +25 | -90 |
| playbook_nobias | neutral | 19 | 26% | **-0.45** | — | -1,288 | +51 | -110 |

## 3. Setups (pooled)

| setup | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|
| astra_h1_vol_trend | 4 | 50% | **+0.75** | — | +1,000 | +554 | -54 |
| gold_breakout | 13 | 46% | **+0.18** | — | +928 | +486 | -284 |
| ict_amd | 12 | 58% | **+0.38** | — | +920 | +183 | -72 |
| dtfx_close_fib | 27 | 63% | **+0.32** | — | +822 | +105 | -96 |
| smc_choch | 1 | 100% | **+1.16** | — | +187 | +187 | — |
| ict_silver_bullet | 3 | 100% | **+0.54** | — | +178 | +59 | — |
| trend_breakout | 5 | 40% | **+0.30** | — | +172 | +271 | -123 |
| c10_afternoon | 6 | 67% | **+0.41** | — | +136 | +105 | -142 |
| dtfx_close_fib_brk | 1 | 100% | **+0.92** | — | +66 | +66 | — |
| smc_mss | 35 | 40% | **-0.02** | -0.21 to +0.15 | +12 | +140 | -93 |
| zone_confluence | 2 | 50% | **-0.09** | — | -28 | +37 | -66 |
| ict_fvg_sweep | 1 | 0% | **-1.02** | — | -52 | — | -52 |
| ema21_rsi55 | 48 | 29% | **-0.04** | -0.27 to +0.33 | -61 | +185 | -78 |
| smc_bos_retest | 21 | 43% | **-0.03** | — | -84 | +144 | -115 |
| dtfx_close_origin | 18 | 50% | **-0.09** | — | -183 | +47 | -67 |
| smc_displacement | 6 | 17% | **-0.67** | — | -290 | +129 | -84 |
| ict_2022 | 8 | 38% | **-0.44** | — | -305 | +32 | -80 |
| ict_turtle_soup | 22 | 45% | **-0.07** | — | -365 | +107 | -119 |
| smc_ifvg | 28 | 43% | **-0.21** | — | -368 | +56 | -65 |
| macd_cross | 9 | 11% | **-0.73** | — | -708 | +36 | -93 |
| dtfx_wick_fib | 37 | 46% | **-0.22** | -0.50 to +0.13 | -818 | +72 | -102 |
| sr_rejection | 72 | 50% | **-0.01** | -0.21 to +0.06 | -944 | +38 | -64 |
| ict_ote | 39 | 46% | **-0.07** | -0.25 to +0.12 | -1,037 | +62 | -103 |

### Setup × instrument: avg R (trades)

| setup | XAUUSD | NDQ | US30 | all |
|---|---|---|---|---|
| smc_choch | [+1.16 (1)] |  |  | [+1.16 (1)] |
| dtfx_close_fib_brk |  |  | [+0.92 (1)] | [+0.92 (1)] |
| astra_h1_vol_trend | [+0.75 (4)] |  |  | [+0.75 (4)] |
| ict_silver_bullet | [+0.54 (3)] |  |  | [+0.54 (3)] |
| c10_afternoon |  | [+0.41 (6)] |  | [+0.41 (6)] |
| ict_amd |  | [+0.48 (7)] | [+0.24 (5)] | +0.38 (12) |
| dtfx_close_fib | [-0.06 (9)] |  | +0.51 (18) | +0.32 (27) |
| trend_breakout |  | [+0.58 (3)] | [-0.12 (2)] | [+0.30 (5)] |
| gold_breakout | +0.18 (13) |  |  | +0.18 (13) |
| sr_rejection | [-0.23 (7)] | +0.08 (23) | -0.02 (42) | -0.01 (72) |
| smc_mss | -0.09 (31) | [+0.54 (4)] |  | -0.02 (35) |
| smc_bos_retest | -0.03 (21) |  |  | -0.03 (21) |
| ema21_rsi55 | +0.13 (27) |  | -0.26 (21) | -0.04 (48) |
| ict_ote | -0.12 (13) | -0.02 (23) | [-0.15 (3)] | -0.07 (39) |
| ict_turtle_soup | -0.07 (22) |  |  | -0.07 (22) |
| dtfx_close_origin |  | -0.09 (18) |  | -0.09 (18) |
| zone_confluence |  | [-0.09 (2)] |  | [-0.09 (2)] |
| smc_ifvg | -0.22 (18) | [+0.38 (6)] | [-1.02 (4)] | -0.21 (28) |
| dtfx_wick_fib | -0.55 (13) | +0.02 (21) | [-0.47 (3)] | -0.22 (37) |
| ict_2022 | [-0.44 (8)] |  |  | [-0.44 (8)] |
| smc_displacement | [-1.00 (5)] | [+1.00 (1)] |  | [-0.67 (6)] |
| macd_cross |  | [-0.79 (4)] | [-0.68 (5)] | [-0.73 (9)] |
| ict_fvg_sweep |  |  | [-1.02 (1)] | [-1.02 (1)] |

### Setup × instrument: net pips

| setup | XAUUSD | NDQ | US30 | all |
|---|---|---|---|---|
| smc_choch | [+187 (1)] |  |  | [+187 (1)] |
| dtfx_close_fib_brk |  |  | [+66 (1)] | [+66 (1)] |
| astra_h1_vol_trend | [+1,000 (4)] |  |  | [+1,000 (4)] |
| ict_silver_bullet | [+178 (3)] |  |  | [+178 (3)] |
| c10_afternoon |  | [+136 (6)] |  | [+136 (6)] |
| ict_amd |  | [+809 (7)] | [+111 (5)] | +920 (12) |
| dtfx_close_fib | [+8 (9)] |  | +814 (18) | +822 (27) |
| trend_breakout |  | [+142 (3)] | [+31 (2)] | [+172 (5)] |
| gold_breakout | +928 (13) |  |  | +928 (13) |
| sr_rejection | [-124 (7)] | -14 (23) | -805 (42) | -944 (72) |
| smc_mss | -27 (31) | [+39 (4)] |  | +12 (35) |
| smc_bos_retest | -84 (21) |  |  | -84 (21) |
| ema21_rsi55 | +802 (27) |  | -863 (21) | -61 (48) |
| ict_ote | -516 (13) | -326 (23) | [-195 (3)] | -1,037 (39) |
| ict_turtle_soup | -365 (22) |  |  | -365 (22) |
| dtfx_close_origin |  | -183 (18) |  | -183 (18) |
| zone_confluence |  | [-28 (2)] |  | [-28 (2)] |
| smc_ifvg | -459 (18) | [+204 (6)] | [-113 (4)] | -368 (28) |
| dtfx_wick_fib | -721 (13) | +327 (21) | [-424 (3)] | -818 (37) |
| ict_2022 | [-305 (8)] |  |  | [-305 (8)] |
| smc_displacement | [-420 (5)] | [+129 (1)] |  | [-290 (6)] |
| macd_cross |  | [-365 (4)] | [-343 (5)] | [-708 (9)] |
| ict_fvg_sweep |  |  | [-52 (1)] | [-52 (1)] |

### Setup × instrument × timeframe (pooled, ≥ 5 trades)

| setup | instrument | tf | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|
| ict_ote | NDQ | 3m | 5 | 60% | **+0.53** | — | +206 | +109 | -61 |
| dtfx_close_fib | US30 | 15m | 15 | 53% | **+0.43** | — | +593 | +149 | -86 |
| c10_afternoon | NDQ | — | 6 | 67% | **+0.41** | — | +136 | +105 | -142 |
| sr_rejection | US30 | 5m | 29 | 59% | **+0.21** | — | +79 | +35 | -43 |
| sr_rejection | NDQ | 5m | 18 | 67% | **+0.19** | — | +119 | +29 | -37 |
| ict_ote | XAUUSD | 5m | 8 | 62% | **+0.19** | — | +41 | +60 | -87 |
| gold_breakout | XAUUSD | — | 13 | 46% | **+0.18** | — | +928 | +486 | -284 |
| ema21_rsi55 | XAUUSD | — | 27 | 30% | **+0.13** | — | +802 | +285 | -78 |
| ict_turtle_soup | XAUUSD | 5m | 10 | 50% | **+0.06** | — | -9 | +128 | -130 |
| dtfx_wick_fib | NDQ | 15m | 17 | 65% | **+0.05** | — | +404 | +90 | -97 |
| ict_amd | NDQ | 5m | 5 | 40% | **+0.03** | — | +60 | +153 | -82 |
| smc_bos_retest | XAUUSD | 5m | 17 | 41% | **-0.03** | — | -169 | +137 | -113 |
| smc_ifvg | XAUUSD | 15m | 6 | 50% | **-0.05** | — | -355 | +42 | -161 |
| dtfx_close_fib | XAUUSD | 3m | 9 | 67% | **-0.06** | — | +8 | +61 | -119 |
| smc_mss | XAUUSD | 3m | 25 | 40% | **-0.08** | — | +21 | +118 | -77 |
| dtfx_close_origin | NDQ | 5m | 18 | 50% | **-0.09** | — | -183 | +47 | -67 |
| smc_mss | XAUUSD | 5m | 6 | 50% | **-0.15** | — | -49 | +108 | -124 |
| ict_ote | NDQ | 5m | 13 | 46% | **-0.15** | — | -232 | +34 | -62 |
| ict_turtle_soup | XAUUSD | 15m | 10 | 40% | **-0.21** | — | -300 | +102 | -118 |
| sr_rejection | XAUUSD | 15m | 7 | 43% | **-0.23** | — | -124 | +43 | -64 |
| ict_ote | NDQ | 15m | 5 | 40% | **-0.24** | — | -300 | +90 | -160 |
| ema21_rsi55 | US30 | — | 21 | 29% | **-0.26** | — | -863 | +52 | -78 |
| smc_ifvg | XAUUSD | 5m | 12 | 33% | **-0.31** | — | -103 | +54 | -40 |
| sr_rejection | US30 | 15m | 5 | 20% | **-0.41** | — | -232 | +32 | -66 |
| ict_2022 | XAUUSD | 3m | 8 | 38% | **-0.44** | — | -305 | +32 | -80 |
| dtfx_wick_fib | XAUUSD | 3m | 8 | 25% | **-0.52** | — | -333 | +67 | -78 |
| dtfx_wick_fib | XAUUSD | 5m | 5 | 20% | **-0.61** | — | -388 | +17 | -101 |
| sr_rejection | US30 | 30m | 8 | 12% | **-0.62** | — | -652 | +141 | -113 |
| ict_ote | XAUUSD | 15m | 5 | 20% | **-0.63** | — | -557 | +32 | -147 |
| macd_cross | US30 | 3m | 5 | 20% | **-0.68** | — | -343 | +36 | -95 |
| smc_displacement | XAUUSD | 3m | 5 | 0% | **-1.00** | — | -420 | — | -84 |

## 4. Hour of entry (NY, pooled)

| hour (NY) | XAUUSD avg R (trades) | XAUUSD net pips | NDQ avg R (trades) | NDQ net pips | US30 avg R (trades) | US30 net pips |
|---|---|---|---|---|---|---|
| 20:00 | -0.07 (7) | +27 | +0.29 (8) | +51 | +0.32 (9) | +398 |
| 21:00 | -0.41 (11) | -917 | -0.32 (7) | +77 | +0.63 (5) | -7 |
| 22:00 | -0.05 (2) | -8 | +0.45 (5) | +182 | +0.70 (3) | +162 |
| 23:00 | -1.01 (5) | -1,002 | -0.63 (3) | -63 | +0.19 (4) | +82 |
| 00:00 | +0.81 (9) | +2,699 | +0.55 (4) | +141 |  |  |
| 01:00 | +0.11 (2) | +54 | -1.00 (1) | -130 |  |  |
| 02:00 | -0.31 (19) | -559 | -0.21 (15) | -398 | -0.10 (11) | -83 |
| 03:00 | -0.19 (25) | -556 | +0.22 (11) | +218 | -0.11 (8) | +4 |
| 04:00 | -0.76 (17) | -1,409 | +0.42 (7) | +20 | -0.05 (6) | -88 |
| 05:00 | -0.30 (2) | -116 | +1.22 (1) | +140 | -0.77 (2) | -197 |
| 06:00 | +2.16 (3) | +1,484 |  |  | -0.35 (6) | -300 |
| 07:00 | -0.33 (2) | -131 | -0.22 (2) | +9 | -0.46 (4) | -226 |
| 08:00 | +0.09 (21) | +65 | -0.49 (7) | -299 | +0.05 (6) | +322 |
| 09:00 | +0.22 (25) | +1,178 | +0.74 (12) | +1,113 | -0.17 (14) | -552 |
| 10:00 | -0.35 (21) | -886 | -0.14 (11) | -10 | -0.50 (6) | -642 |
| 11:00 | +0.07 (2) | +22 | -1.01 (3) | -364 | +0.03 (5) | -460 |
| 12:00 | -0.19 (2) | -134 |  |  |  |  |
| 13:00 | +0.74 (7) | +435 | +0.22 (11) | +122 | +0.07 (4) | +96 |
| 14:00 | +0.02 (10) | +133 | +0.03 (7) | -2 | +0.08 (7) | -133 |
| 15:00 | -0.44 (3) | -296 | +0.54 (3) | +62 | -0.56 (5) | -149 |

### Setup × session: avg R (trades)

| setup | Asia 20–02 | London 02–08 | NY AM 08–12 | NY PM 12–16 | all |
|---|---|---|---|---|---|
| smc_choch |  |  | [+1.16 (1)] |  | [+1.16 (1)] |
| dtfx_close_fib_brk | [+0.92 (1)] |  |  |  | [+0.92 (1)] |
| astra_h1_vol_trend |  |  | [+1.06 (3)] | [-0.17 (1)] | [+0.75 (4)] |
| ict_silver_bullet |  | [+0.58 (2)] | [+0.47 (1)] |  | [+0.54 (3)] |
| c10_afternoon |  |  |  | [+0.41 (6)] | [+0.41 (6)] |
| ict_amd |  | [+0.37 (8)] | [+0.39 (4)] |  | +0.38 (12) |
| dtfx_close_fib | [+0.92 (8)] | [-0.15 (6)] | [-0.10 (9)] | [+0.77 (4)] | +0.32 (27) |
| trend_breakout | [-0.41 (3)] | [-1.00 (1)] | [+3.75 (1)] |  | [+0.30 (5)] |
| gold_breakout | +0.47 (10) | [-1.00 (1)] | [-0.68 (2)] |  | +0.18 (13) |
| sr_rejection | +0.09 (26) | -0.05 (17) | +0.05 (22) | [-0.48 (7)] | -0.01 (72) |
| smc_mss |  | -0.31 (16) | +0.24 (15) | [+0.15 (4)] | -0.02 (35) |
| smc_bos_retest | [-0.46 (8)] | [-0.85 (4)] | [+0.92 (6)] | [+0.32 (3)] | -0.03 (21) |
| ema21_rsi55 |  | +0.02 (28) | -0.11 (15) | [-0.20 (5)] | -0.04 (48) |
| ict_ote |  | +0.02 (16) | -0.44 (13) | +0.29 (10) | -0.07 (39) |
| ict_turtle_soup |  | [-0.37 (7)] | -0.10 (10) | [+0.40 (5)] | -0.07 (22) |
| dtfx_close_origin | [-0.11 (5)] | [+0.43 (5)] | [-1.00 (4)] | [+0.21 (4)] | -0.09 (18) |
| zone_confluence | [+0.82 (1)] | [-1.00 (1)] |  |  | [-0.09 (2)] |
| smc_ifvg | +0.04 (10) | [-0.74 (7)] | +0.00 (10) | [-1.03 (1)] | -0.21 (28) |
| dtfx_wick_fib | [-0.02 (9)] | -0.39 (13) | [-0.34 (9)] | [+0.03 (6)] | -0.22 (37) |
| ict_2022 |  | [-0.40 (5)] | [-0.51 (3)] |  | [-0.44 (8)] |
| smc_displacement | [-1.00 (3)] | [+0.00 (2)] | [-1.00 (1)] |  | [-0.67 (6)] |
| macd_cross | [-0.15 (1)] | [-1.00 (2)] | [-1.00 (3)] | [-0.47 (3)] | [-0.73 (9)] |
| ict_fvg_sweep |  |  | [-1.02 (1)] |  | [-1.02 (1)] |

## 5. Per book: setup × instrument × timeframe

### C10 afternoon

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| c10_afternoon | NDQ | — | n/a | 6 | 67% | **+0.41** | — | +136 | +105 | -142 |

### EMA21 + RSI 55

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| ema21_rsi55 | XAUUSD | — | n/a | 27 | 30% | **+0.13** | — | +802 | +285 | -78 |
| ema21_rsi55 | US30 | — | n/a | 21 | 29% | **-0.26** | — | -863 | +52 | -78 |

### Gold breakout

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| gold_breakout | XAUUSD | — | n/a | 13 | 46% | **+0.18** | — | +928 | +486 | -284 |

### Gold H1 trend

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| astra_h1_vol_trend | XAUUSD | — | n/a | 4 | 50% | **+0.75** | — | +1,000 | +554 | -54 |

### Playbook

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| trend_breakout | NDQ | 15m | aligned | 1 | 100% | **+3.75** | — | +453 | +453 | — |
| smc_mss | NDQ | 5m | aligned | 2 | 50% | **+2.08** | — | +450 | +459 | -9 |
| smc_mss | XAUUSD | 5m | aligned | 3 | 100% | **+0.71** | — | +323 | +108 | — |
| ict_turtle_soup | XAUUSD | 15m | aligned | 5 | 60% | **+0.33** | — | +255 | +130 | -68 |
| smc_mss | XAUUSD | 3m | aligned | 19 | 47% | **-0.01** | — | +235 | +118 | -83 |
| dtfx_close_fib | US30 | 15m | aligned | 9 | 56% | **+0.42** | — | +197 | +120 | -100 |
| smc_choch | XAUUSD | 3m | aligned | 1 | 100% | **+1.16** | — | +187 | +187 | — |
| dtfx_wick_fib | NDQ | 15m | aligned | 14 | 57% | **-0.09** | — | +150 | +92 | -97 |
| ict_silver_bullet | XAUUSD | 5m | aligned | 2 | 100% | **+0.58** | — | +129 | +64 | — |
| trend_breakout | US30 | 15m | aligned | 1 | 100% | **+0.77** | — | +90 | +90 | — |
| dtfx_close_fib | US30 | 3m | aligned | 1 | 100% | **+0.99** | — | +89 | +89 | — |
| ict_amd | US30 | 5m | aligned | 1 | 100% | **+1.52** | — | +75 | +75 | — |
| ict_amd | US30 | 3m | aligned | 4 | 50% | **-0.08** | — | +35 | +76 | -58 |
| ict_amd | NDQ | 5m | aligned | 3 | 33% | **+0.16** | — | +33 | +146 | -56 |
| dtfx_close_fib | XAUUSD | 3m | aligned | 3 | 67% | **-0.20** | — | +2 | +42 | -82 |
| dtfx_wick_fib | NDQ | 5m | aligned | 2 | 50% | **+0.00** | — | -7 | +55 | -62 |
| ict_turtle_soup | XAUUSD | 3m | aligned | 2 | 50% | **-0.05** | — | -56 | +19 | -75 |
| ict_ote | NDQ | 3m | aligned | 2 | 50% | **-0.27** | — | -62 | +42 | -104 |
| sr_rejection | NDQ | 30m | aligned | 1 | 0% | **-1.00** | — | -92 | — | -92 |
| ict_turtle_soup | XAUUSD | 5m | aligned | 7 | 43% | **-0.10** | — | -94 | +98 | -97 |
| dtfx_wick_fib | XAUUSD | 5m | aligned | 1 | 0% | **-0.87** | — | -96 | — | -96 |
| smc_bos_retest | XAUUSD | 15m | aligned | 1 | 0% | **-1.00** | — | -116 | — | -116 |
| dtfx_close_origin | NDQ | 5m | aligned | 3 | 33% | **-0.22** | — | -166 | +12 | -89 |
| dtfx_wick_fib | US30 | 15m | aligned | 1 | 0% | **-1.00** | — | -210 | — | -210 |
| smc_ifvg | XAUUSD | 15m | aligned | 4 | 50% | **-0.12** | — | -226 | +37 | -150 |
| sr_rejection | US30 | 30m | aligned | 4 | 0% | **-1.00** | — | -275 | — | -69 |
| ict_2022 | XAUUSD | 3m | aligned | 7 | 29% | **-0.58** | — | -355 | +24 | -80 |
| macd_cross | NDQ | 5m | aligned | 4 | 0% | **-0.79** | — | -365 | — | -91 |
| smc_displacement | XAUUSD | 3m | aligned | 5 | 0% | **-1.00** | — | -420 | — | -84 |
| dtfx_wick_fib | XAUUSD | 3m | aligned | 7 | 14% | **-0.79** | — | -443 | +24 | -78 |
| smc_bos_retest | XAUUSD | 5m | aligned | 12 | 42% | **-0.21** | — | -552 | +78 | -134 |

### Playbook, all hours

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| smc_mss | NDQ | 5m | aligned | 2 | 50% | **+2.08** | — | +450 | +459 | -9 |
| dtfx_wick_fib | NDQ | 15m | aligned | 4 | 75% | **+0.40** | — | +381 | +170 | -129 |
| trend_breakout | NDQ | 15m | aligned | 2 | 50% | **+1.37** | — | +323 | +453 | -130 |
| ict_turtle_soup | XAUUSD | 15m | aligned | 1 | 100% | **+1.89** | — | +276 | +276 | — |
| smc_mss | XAUUSD | 5m | aligned | 2 | 100% | **+0.84** | — | +263 | +132 | — |
| dtfx_close_fib | XAUUSD | 3m | aligned | 1 | 100% | **+1.64** | — | +183 | +183 | — |
| dtfx_close_fib | US30 | 3m | aligned | 2 | 100% | **+0.97** | — | +164 | +82 | — |
| dtfx_close_fib | US30 | 15m | aligned | 6 | 67% | **+0.55** | — | +152 | +127 | -178 |
| ict_silver_bullet | XAUUSD | 5m | aligned | 2 | 100% | **+0.57** | — | +128 | +64 | — |
| smc_mss | XAUUSD | 3m | aligned | 2 | 50% | **+0.29** | — | +91 | +123 | -32 |
| dtfx_close_fib_brk | US30 | 3m | aligned | 1 | 100% | **+0.92** | — | +66 | +66 | — |
| smc_bos_retest | XAUUSD | 5m | aligned | 1 | 0% | **-0.11** | — | -20 | — | -20 |
| ict_amd | NDQ | 5m | aligned | 1 | 0% | **-0.29** | — | -20 | — | -20 |
| trend_breakout | US30 | 15m | aligned | 1 | 0% | **-1.00** | — | -59 | — | -59 |
| ict_ote | NDQ | 3m | aligned | 2 | 50% | **-0.27** | — | -62 | +42 | -104 |
| ict_2022 | XAUUSD | 3m | aligned | 1 | 0% | **-1.00** | — | -91 | — | -91 |
| dtfx_wick_fib | XAUUSD | 5m | aligned | 1 | 0% | **-0.87** | — | -96 | — | -96 |
| macd_cross | US30 | 3m | aligned | 1 | 0% | **-1.00** | — | -112 | — | -112 |
| smc_bos_retest | XAUUSD | 15m | aligned | 1 | 0% | **-1.00** | — | -138 | — | -138 |
| ict_turtle_soup | XAUUSD | 5m | aligned | 1 | 0% | **-1.00** | — | -160 | — | -160 |
| dtfx_close_origin | NDQ | 5m | aligned | 8 | 50% | **-0.16** | — | -209 | +18 | -70 |
| sr_rejection | US30 | 30m | aligned | 1 | 0% | **-1.00** | — | -287 | — | -287 |

### Playbook, no bias rule

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| smc_mss | NDQ | 5m | aligned | 1 | 100% | **+4.20** | — | +460 | +460 | — |
| smc_bos_retest | XAUUSD | 15m | aligned | 2 | 100% | **+0.98** | — | +339 | +170 | — |
| ict_turtle_soup | XAUUSD | 15m | aligned | 1 | 100% | **+1.89** | — | +276 | +276 | — |
| smc_mss | XAUUSD | 5m | aligned | 2 | 100% | **+0.84** | — | +262 | +131 | — |
| smc_bos_retest | XAUUSD | 5m | counter | 1 | 100% | **+1.45** | — | +256 | +256 | — |
| smc_mss | XAUUSD | 3m | aligned | 3 | 67% | **+0.51** | — | +200 | +116 | -32 |
| dtfx_close_fib | US30 | 15m | counter | 2 | 50% | **+0.28** | — | +200 | +286 | -87 |
| ict_ote | NDQ | 3m | counter | 2 | 50% | **+0.81** | — | +181 | +198 | -18 |
| dtfx_close_fib | US30 | 3m | aligned | 2 | 100% | **+0.97** | — | +164 | +82 | — |
| dtfx_close_fib | US30 | 15m | aligned | 4 | 75% | **+0.79** | — | +134 | +126 | -243 |
| smc_displacement | NDQ | 5m | counter | 1 | 100% | **+1.00** | — | +129 | +129 | — |
| smc_bos_retest | XAUUSD | 5m | aligned | 4 | 25% | **+0.14** | — | +127 | +312 | -62 |
| ict_turtle_soup | XAUUSD | 5m | aligned | 1 | 100% | **+0.57** | — | +112 | +112 | — |
| dtfx_wick_fib | XAUUSD | 3m | aligned | 1 | 100% | **+1.36** | — | +110 | +110 | — |
| ict_amd | US30 | 3m | aligned | 1 | 100% | **+1.47** | — | +93 | +93 | — |
| trend_breakout | US30 | 15m | aligned | 1 | 100% | **+0.77** | — | +90 | +90 | — |
| ict_silver_bullet | XAUUSD | 5m | aligned | 2 | 100% | **+0.48** | — | +88 | +44 | — |
| ict_amd | NDQ | 3m | counter | 1 | 100% | **+0.55** | — | +88 | +88 | — |
| sr_rejection | US30 | 30m | neutral | 2 | 50% | **+0.52** | — | +85 | +141 | -55 |
| dtfx_close_fib | US30 | 3m | neutral | 1 | 100% | **+0.77** | — | +58 | +58 | — |
| dtfx_close_fib | XAUUSD | 3m | counter | 1 | 100% | **+0.21** | — | +53 | +53 | — |
| macd_cross | US30 | 3m | aligned | 1 | 100% | **+0.59** | — | +36 | +36 | — |
| ict_amd | NDQ | 5m | counter | 2 | 50% | **-0.16** | — | +27 | +161 | -134 |
| dtfx_wick_fib | US30 | 3m | neutral | 1 | 100% | **+0.60** | — | +22 | +22 | — |
| dtfx_wick_fib | NDQ | 5m | neutral | 1 | 100% | **+0.11** | — | +13 | +13 | — |
| dtfx_close_origin | NDQ | 5m | counter | 9 | 44% | **-0.10** | — | -14 | +77 | -64 |
| ict_amd | NDQ | 5m | aligned | 1 | 0% | **-0.29** | — | -20 | — | -20 |
| ict_turtle_soup | XAUUSD | 5m | counter | 2 | 50% | **+0.35** | — | -27 | +232 | -260 |
| ict_2022 | XAUUSD | 3m | aligned | 2 | 50% | **-0.23** | — | -41 | +49 | -91 |
| ict_ote | NDQ | 3m | aligned | 2 | 50% | **-0.27** | — | -62 | +42 | -104 |
| zone_confluence | NDQ | 3m | aligned | 1 | 0% | **-1.00** | — | -66 | — | -66 |
| dtfx_wick_fib | NDQ | 5m | counter | 1 | 0% | **-0.50** | — | -83 | — | -83 |
| macd_cross | US30 | 3m | counter | 1 | 0% | **-1.00** | — | -87 | — | -87 |
| dtfx_wick_fib | XAUUSD | 5m | aligned | 1 | 0% | **-0.87** | — | -96 | — | -96 |
| dtfx_close_fib | XAUUSD | 3m | neutral | 1 | 0% | **-1.00** | — | -137 | — | -137 |
| dtfx_wick_fib | XAUUSD | 5m | neutral | 1 | 0% | **-1.00** | — | -138 | — | -138 |
| sr_rejection | US30 | 30m | counter | 1 | 0% | **-1.00** | — | -175 | — | -175 |
| trend_breakout | NDQ | 15m | aligned | 1 | 0% | **-1.00** | — | -181 | — | -181 |
| dtfx_wick_fib | US30 | 15m | aligned | 1 | 0% | **-1.00** | — | -210 | — | -210 |
| dtfx_close_origin | NDQ | 5m | aligned | 5 | 40% | **-0.23** | — | -220 | +15 | -83 |
| dtfx_wick_fib | US30 | 15m | counter | 1 | 0% | **-1.00** | — | -237 | — | -237 |
| smc_mss | XAUUSD | 3m | neutral | 4 | 0% | **-0.57** | — | -265 | — | -66 |
| smc_mss | XAUUSD | 5m | neutral | 3 | 0% | **-1.00** | — | -372 | — | -124 |
| smc_mss | NDQ | 5m | counter | 2 | 0% | **-1.00** | — | -411 | — | -205 |
| ict_turtle_soup | XAUUSD | 15m | neutral | 5 | 20% | **-0.76** | — | -555 | +19 | -143 |

### Playbook + no bias, all hours

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| ict_amd | NDQ | 3m | aligned | 1 | 100% | **+2.65** | — | +661 | +661 | — |
| smc_mss | XAUUSD | 5m | aligned | 2 | 100% | **+0.84** | — | +262 | +131 | — |
| ict_amd | NDQ | 5m | counter | 1 | 100% | **+0.69** | — | +161 | +161 | — |
| smc_displacement | NDQ | 5m | counter | 1 | 100% | **+1.00** | — | +129 | +129 | — |
| smc_mss | XAUUSD | 3m | aligned | 1 | 100% | **+0.70** | — | +123 | +123 | — |
| dtfx_close_origin | NDQ | 5m | counter | 5 | 60% | **+0.14** | — | +97 | +78 | -69 |
| ict_amd | US30 | 3m | aligned | 1 | 100% | **+1.47** | — | +93 | +93 | — |
| ict_amd | NDQ | 3m | counter | 1 | 100% | **+0.55** | — | +88 | +88 | — |
| ict_ote | NDQ | 3m | counter | 2 | 50% | **+0.76** | — | +69 | +87 | -18 |
| dtfx_close_fib_brk | US30 | 3m | aligned | 1 | 100% | **+0.92** | — | +66 | +66 | — |
| dtfx_close_fib | US30 | 3m | neutral | 1 | 100% | **+0.77** | — | +58 | +58 | — |
| dtfx_close_fib | XAUUSD | 3m | counter | 1 | 100% | **+0.21** | — | +53 | +53 | — |
| dtfx_wick_fib | NDQ | 15m | aligned | 1 | 100% | **+0.32** | — | +51 | +51 | — |
| trend_breakout | US30 | 15m | aligned | 2 | 50% | **-0.12** | — | +31 | +90 | -59 |
| dtfx_wick_fib | US30 | 3m | neutral | 1 | 100% | **+0.60** | — | +22 | +22 | — |
| ict_turtle_soup | XAUUSD | 15m | neutral | 1 | 100% | **+0.21** | — | +19 | +19 | — |
| dtfx_wick_fib | NDQ | 5m | neutral | 1 | 100% | **+0.11** | — | +13 | +13 | — |
| zone_confluence | NDQ | 3m | aligned | 2 | 50% | **-0.09** | — | -29 | +37 | -66 |
| ict_ote | NDQ | 3m | aligned | 2 | 50% | **-0.27** | — | -62 | +42 | -104 |
| dtfx_wick_fib | XAUUSD | 5m | counter | 1 | 0% | **-0.21** | — | -67 | — | -67 |
| dtfx_wick_fib | NDQ | 5m | counter | 1 | 0% | **-0.50** | — | -83 | — | -83 |
| dtfx_close_fib | US30 | 15m | counter | 2 | 0% | **-0.50** | — | -87 | — | -43 |
| dtfx_close_fib | XAUUSD | 3m | neutral | 3 | 67% | **-0.26** | — | -93 | +22 | -137 |
| smc_mss | XAUUSD | 3m | neutral | 3 | 0% | **-0.37** | — | -162 | — | -54 |
| dtfx_close_origin | NDQ | 5m | aligned | 1 | 0% | **-1.00** | — | -171 | — | -171 |
| macd_cross | US30 | 3m | counter | 2 | 0% | **-1.00** | — | -180 | — | -90 |
| dtfx_wick_fib | US30 | 15m | aligned | 1 | 0% | **-1.00** | — | -210 | — | -210 |
| dtfx_wick_fib | XAUUSD | 5m | neutral | 3 | 33% | **-0.65** | — | -225 | +17 | -121 |
| dtfx_wick_fib | US30 | 15m | counter | 1 | 0% | **-1.00** | — | -237 | — | -237 |
| sr_rejection | US30 | 30m | aligned | 1 | 0% | **-1.00** | — | -287 | — | -287 |
| trend_breakout | NDQ | 15m | aligned | 2 | 0% | **-1.00** | — | -311 | — | -156 |
| smc_mss | NDQ | 5m | counter | 2 | 0% | **-0.94** | — | -385 | — | -193 |

### Practice account

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| c10_afternoon | NDQ | — | n/a | 5 | 80% | **+0.78** | — | +216 | +115 | -243 |
| smc_ifvg | NDQ | 15m | aligned | 3 | 67% | **+0.06** | — | +124 | +127 | -129 |
| sr_rejection | NDQ | 5m | aligned | 18 | 67% | **+0.19** | — | +119 | +29 | -37 |
| smc_ifvg | NDQ | 5m | aligned | 3 | 100% | **+0.71** | — | +79 | +26 | — |
| sr_rejection | US30 | 5m | aligned | 29 | 59% | **+0.21** | — | +79 | +35 | -43 |
| ict_ote | XAUUSD | 5m | aligned | 8 | 62% | **+0.19** | — | +41 | +60 | -87 |
| sr_rejection | NDQ | 15m | aligned | 4 | 50% | **-0.16** | — | -41 | +61 | -81 |
| ict_fvg_sweep | US30 | 5m | aligned | 1 | 0% | **-1.02** | — | -52 | — | -52 |
| smc_ifvg | XAUUSD | 5m | aligned | 12 | 33% | **-0.31** | — | -103 | +54 | -40 |
| smc_ifvg | US30 | 5m | aligned | 4 | 0% | **-1.02** | — | -113 | — | -28 |
| sr_rejection | XAUUSD | 15m | aligned | 7 | 43% | **-0.23** | — | -124 | +43 | -64 |
| smc_ifvg | XAUUSD | 15m | aligned | 2 | 50% | **+0.09** | — | -130 | +52 | -182 |
| ict_ote | US30 | 15m | aligned | 3 | 33% | **-0.15** | — | -195 | +73 | -134 |
| ict_ote | NDQ | 5m | aligned | 13 | 46% | **-0.15** | — | -232 | +34 | -62 |
| sr_rejection | US30 | 15m | aligned | 5 | 20% | **-0.41** | — | -232 | +32 | -66 |
| ict_ote | NDQ | 15m | aligned | 5 | 40% | **-0.24** | — | -300 | +90 | -160 |
| ict_ote | XAUUSD | 15m | aligned | 5 | 20% | **-0.63** | — | -557 | +32 | -147 |

