# Trade atlas: what every book has actually done (forward)

503 closed trades in 9 books, 2026-10-05 → 2026-11-06 (pooled across books, the same signal counted once: 413). Pips = net P&L ÷ ($ per pip × all units traded), as the dashboard. Bias = the bias at entry: the no-bias books record what the rule *would* have said, so they are where neutral and counter-bias trades show up; rule-based books (C10, gold breakout, EMA/RSI, …) have no bias (n/a).

**Samples are small.** A slice needs about 100 trades before its average means much; most here have far fewer. Read this as what happened, and use the history atlas for what tends to happen.

## 1. Books

| book | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|
| h1_vol_trend | 4 | 50% | **+0.75** | — | +100 | +55 | -5 |
| c10_afternoon | 6 | 67% | **+0.41** | — | +68 | +53 | -71 |
| playbook_allhours | 43 | 53% | **+0.28** | — | +304 | +101 | -101 |
| gold_breakout | 13 | 46% | **+0.18** | — | +93 | +49 | -28 |
| playbook_nobias | 83 | 48% | **+0.09** | — | +366 | +85 | -70 |
| practice | 127 | 50% | **-0.02** | -0.20 to +0.07 | -1,132 | +36 | -54 |
| ema21_rsi55 | 48 | 29% | **-0.04** | -0.27 to +0.33 | -1,646 | +61 | -73 |
| playbook_nobias_allhours | 48 | 48% | **-0.04** | — | -1,176 | +62 | -104 |
| playbook | 131 | 44% | **-0.09** | -0.32 to +0.29 | +59 | +57 | -43 |

## 2. Bias at entry (pooled, each signal once)

| bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|
| n/a | 71 | 37% | **+0.08** | -0.24 to +0.47 | -1,385 | +56 | -63 |
| counter | 31 | 45% | **+0.04** | — | -514 | +81 | -97 |
| aligned | 286 | 48% | **-0.03** | -0.20 to +0.11 | -1,088 | +50 | -53 |
| neutral | 25 | 32% | **-0.43** | — | +167 | +57 | -17 |

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
| ict_turtle_soup | +0.10 (15) | [-0.76 (5)] | [+0.35 (2)] |  | -0.07 (22) |
| ict_ote | -0.18 (35) |  | [+1.07 (3)] |  | -0.08 (38) |
| dtfx_close_origin | [-0.16 (8)] |  | -0.03 (10) |  | -0.09 (18) |
| zone_confluence | [-0.09 (2)] |  |  |  | [-0.09 (2)] |
| smc_ifvg | -0.21 (28) |  |  |  | -0.21 (28) |
| dtfx_wick_fib | -0.20 (28) | [-0.25 (5)] | [-0.57 (3)] |  | -0.24 (36) |
| ict_2022 | [-0.44 (8)] |  |  |  | [-0.44 (8)] |
| smc_displacement | [-1.00 (5)] |  | [+1.00 (1)] |  | [-0.67 (6)] |
| macd_cross | [-0.83 (5)] |  | [-1.00 (1)] |  | [-0.86 (6)] |
| ict_fvg_sweep | [-1.02 (1)] |  |  |  | [-1.02 (1)] |

### Per book × bias

| book | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|
| practice | n/a | 5 | 80% | **+0.78** | — | +108 | +57 | -122 |
| h1_vol_trend | n/a | 4 | 50% | **+0.75** | — | +100 | +55 | -5 |
| c10_afternoon | n/a | 6 | 67% | **+0.41** | — | +68 | +53 | -71 |
| playbook_nobias | aligned | 38 | 61% | **+0.40** | — | +615 | +81 | -84 |
| playbook_allhours | aligned | 43 | 53% | **+0.28** | — | +304 | +101 | -101 |
| gold_breakout | n/a | 13 | 46% | **+0.18** | — | +93 | +49 | -28 |
| playbook_nobias_allhours | aligned | 16 | 50% | **+0.06** | — | -552 | +111 | -180 |
| playbook_nobias | counter | 26 | 46% | **+0.02** | — | -439 | +89 | -108 |
| ema21_rsi55 | n/a | 48 | 29% | **-0.04** | -0.27 to +0.33 | -1,646 | +61 | -73 |
| playbook_nobias_allhours | counter | 19 | 42% | **-0.05** | — | -744 | +44 | -100 |
| practice | aligned | 122 | 49% | **-0.05** | -0.22 to +0.01 | -1,240 | +34 | -53 |
| playbook | aligned | 131 | 44% | **-0.09** | -0.32 to +0.29 | +59 | +57 | -43 |
| playbook_nobias_allhours | neutral | 13 | 54% | **-0.17** | — | +120 | +25 | -9 |
| playbook_nobias | neutral | 19 | 26% | **-0.45** | — | +190 | +90 | -19 |

## 3. Setups (pooled)

| setup | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|
| dtfx_close_fib | 27 | 63% | **+0.32** | — | +1,629 | +169 | -124 |
| ict_amd | 12 | 58% | **+0.38** | — | +626 | +140 | -71 |
| dtfx_close_fib_brk | 1 | 100% | **+0.92** | — | +133 | +133 | — |
| trend_breakout | 5 | 40% | **+0.30** | — | +133 | +203 | -91 |
| astra_h1_vol_trend | 4 | 50% | **+0.75** | — | +100 | +55 | -5 |
| gold_breakout | 13 | 46% | **+0.18** | — | +93 | +49 | -28 |
| c10_afternoon | 6 | 67% | **+0.41** | — | +68 | +53 | -71 |
| smc_displacement | 6 | 17% | **-0.67** | — | +23 | +65 | -8 |
| smc_choch | 1 | 100% | **+1.16** | — | +19 | +19 | — |
| ict_silver_bullet | 3 | 100% | **+0.54** | — | +18 | +6 | — |
| smc_mss | 35 | 40% | **-0.02** | -0.21 to +0.15 | +17 | +27 | -17 |
| smc_bos_retest | 21 | 43% | **-0.03** | — | -8 | +14 | -11 |
| zone_confluence | 2 | 50% | **-0.09** | — | -14 | +19 | -33 |
| ict_2022 | 8 | 38% | **-0.44** | — | -31 | +3 | -8 |
| ict_turtle_soup | 22 | 45% | **-0.07** | — | -37 | +11 | -12 |
| dtfx_close_origin | 18 | 50% | **-0.09** | — | -91 | +23 | -33 |
| ict_fvg_sweep | 1 | 0% | **-1.02** | — | -104 | — | -104 |
| smc_ifvg | 28 | 43% | **-0.21** | — | -170 | +17 | -23 |
| macd_cross | 6 | 0% | **-0.86** | — | -538 | — | -90 |
| ict_ote | 38 | 45% | **-0.08** | -0.25 to +0.10 | -627 | +30 | -54 |
| dtfx_wick_fib | 36 | 44% | **-0.24** | -0.54 to +0.13 | -783 | +35 | -67 |
| sr_rejection | 72 | 50% | **-0.01** | -0.21 to +0.06 | -1,630 | +50 | -95 |
| ema21_rsi55 | 48 | 29% | **-0.04** | -0.27 to +0.33 | -1,646 | +61 | -73 |

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
| ict_turtle_soup | -0.07 (22) |  |  | -0.07 (22) |
| ict_ote | -0.12 (13) | -0.04 (22) | [-0.15 (3)] | -0.08 (38) |
| dtfx_close_origin |  | -0.09 (18) |  | -0.09 (18) |
| zone_confluence |  | [-0.09 (2)] |  | [-0.09 (2)] |
| smc_ifvg | -0.22 (18) | [+0.38 (6)] | [-1.02 (4)] | -0.21 (28) |
| dtfx_wick_fib | -0.55 (13) | +0.00 (20) | [-0.47 (3)] | -0.24 (36) |
| ict_2022 | [-0.44 (8)] |  |  | [-0.44 (8)] |
| smc_displacement | [-1.00 (5)] | [+1.00 (1)] |  | [-0.67 (6)] |
| macd_cross |  | [-0.79 (4)] | [-1.00 (2)] | [-0.86 (6)] |
| ict_fvg_sweep |  |  | [-1.02 (1)] | [-1.02 (1)] |

### Setup × instrument: net pips

| setup | XAUUSD | NDQ | US30 | all |
|---|---|---|---|---|
| smc_choch | [+19 (1)] |  |  | [+19 (1)] |
| dtfx_close_fib_brk |  |  | [+133 (1)] | [+133 (1)] |
| astra_h1_vol_trend | [+100 (4)] |  |  | [+100 (4)] |
| ict_silver_bullet | [+18 (3)] |  |  | [+18 (3)] |
| c10_afternoon |  | [+68 (6)] |  | [+68 (6)] |
| ict_amd |  | [+404 (7)] | [+222 (5)] | +626 (12) |
| dtfx_close_fib | [+1 (9)] |  | +1,628 (18) | +1,629 (27) |
| trend_breakout |  | [+71 (3)] | [+62 (2)] | [+133 (5)] |
| gold_breakout | +93 (13) |  |  | +93 (13) |
| sr_rejection | [-12 (7)] | -7 (23) | -1,611 (42) | -1,630 (72) |
| smc_mss | -3 (31) | [+20 (4)] |  | +17 (35) |
| smc_bos_retest | -8 (21) |  |  | -8 (21) |
| ema21_rsi55 | +80 (27) |  | -1,726 (21) | -1,646 (48) |
| ict_turtle_soup | -37 (22) |  |  | -37 (22) |
| ict_ote | -52 (13) | -184 (22) | [-391 (3)] | -627 (38) |
| dtfx_close_origin |  | -91 (18) |  | -91 (18) |
| zone_confluence |  | [-14 (2)] |  | [-14 (2)] |
| smc_ifvg | -46 (18) | [+102 (6)] | [-226 (4)] | -170 (28) |
| dtfx_wick_fib | -72 (13) | +138 (20) | [-849 (3)] | -783 (36) |
| ict_2022 | [-31 (8)] |  |  | [-31 (8)] |
| smc_displacement | [-42 (5)] | [+65 (1)] |  | [+23 (6)] |
| macd_cross |  | [-182 (4)] | [-356 (2)] | [-538 (6)] |
| ict_fvg_sweep |  |  | [-104 (1)] | [-104 (1)] |

### Setup × instrument × timeframe (pooled, ≥ 5 trades)

| setup | instrument | tf | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|
| dtfx_close_fib | US30 | 15m | 15 | 53% | **+0.43** | — | +1,186 | +298 | -172 |
| c10_afternoon | NDQ | — | 6 | 67% | **+0.41** | — | +68 | +53 | -71 |
| sr_rejection | US30 | 5m | 29 | 59% | **+0.21** | — | +158 | +70 | -86 |
| sr_rejection | NDQ | 5m | 18 | 67% | **+0.19** | — | +60 | +14 | -19 |
| ict_ote | XAUUSD | 5m | 8 | 62% | **+0.19** | — | +4 | +6 | -9 |
| gold_breakout | XAUUSD | — | 13 | 46% | **+0.18** | — | +93 | +49 | -28 |
| ema21_rsi55 | XAUUSD | — | 27 | 30% | **+0.13** | — | +80 | +29 | -8 |
| ict_turtle_soup | XAUUSD | 5m | 10 | 50% | **+0.06** | — | -1 | +13 | -13 |
| ict_amd | NDQ | 5m | 5 | 40% | **+0.03** | — | +30 | +77 | -41 |
| dtfx_wick_fib | NDQ | 15m | 16 | 62% | **+0.03** | — | +177 | +47 | -49 |
| smc_bos_retest | XAUUSD | 5m | 17 | 41% | **-0.03** | — | -17 | +14 | -11 |
| smc_ifvg | XAUUSD | 15m | 6 | 50% | **-0.05** | — | -36 | +4 | -16 |
| dtfx_close_fib | XAUUSD | 3m | 9 | 67% | **-0.06** | — | +1 | +6 | -12 |
| smc_mss | XAUUSD | 3m | 25 | 40% | **-0.08** | — | +2 | +12 | -8 |
| dtfx_close_origin | NDQ | 5m | 18 | 50% | **-0.09** | — | -91 | +23 | -33 |
| smc_mss | XAUUSD | 5m | 6 | 50% | **-0.15** | — | -5 | +11 | -12 |
| ict_ote | NDQ | 5m | 13 | 46% | **-0.15** | — | -116 | +17 | -31 |
| ict_turtle_soup | XAUUSD | 15m | 10 | 40% | **-0.21** | — | -30 | +10 | -12 |
| sr_rejection | XAUUSD | 15m | 7 | 43% | **-0.23** | — | -12 | +4 | -6 |
| ict_ote | NDQ | 15m | 5 | 40% | **-0.24** | — | -150 | +45 | -80 |
| ema21_rsi55 | US30 | — | 21 | 29% | **-0.26** | — | -1,726 | +104 | -157 |
| smc_ifvg | XAUUSD | 5m | 12 | 33% | **-0.31** | — | -10 | +5 | -4 |
| sr_rejection | US30 | 15m | 5 | 20% | **-0.41** | — | -464 | +65 | -132 |
| ict_2022 | XAUUSD | 3m | 8 | 38% | **-0.44** | — | -31 | +3 | -8 |
| dtfx_wick_fib | XAUUSD | 3m | 8 | 25% | **-0.52** | — | -33 | +7 | -8 |
| dtfx_wick_fib | XAUUSD | 5m | 5 | 20% | **-0.61** | — | -39 | +2 | -10 |
| sr_rejection | US30 | 30m | 8 | 12% | **-0.62** | — | -1,304 | +281 | -227 |
| ict_ote | XAUUSD | 15m | 5 | 20% | **-0.63** | — | -56 | +3 | -15 |
| smc_displacement | XAUUSD | 3m | 5 | 0% | **-1.00** | — | -42 | — | -8 |

## 4. Hour of entry (NY, pooled)

| hour (NY) | XAUUSD avg R (trades) | XAUUSD net pips | NDQ avg R (trades) | NDQ net pips | US30 avg R (trades) | US30 net pips |
|---|---|---|---|---|---|---|
| 20:00 | -0.07 (7) | +3 | +0.29 (8) | +26 | +0.32 (9) | +795 |
| 21:00 | -0.41 (11) | -92 | -0.32 (7) | +38 | +0.63 (5) | -14 |
| 22:00 | -0.05 (2) | -1 | +0.45 (5) | +91 | +0.70 (3) | +323 |
| 23:00 | -1.01 (5) | -100 | -0.63 (3) | -32 | +0.19 (4) | +164 |
| 00:00 | +0.81 (9) | +270 | +0.55 (4) | +71 |  |  |
| 01:00 | +0.11 (2) | +5 | -1.00 (1) | -65 |  |  |
| 02:00 | -0.31 (19) | -56 | -0.21 (15) | -199 | -0.10 (11) | -165 |
| 03:00 | -0.19 (25) | -56 | +0.22 (11) | +109 | -0.11 (8) | +8 |
| 04:00 | -0.76 (17) | -141 | +0.42 (7) | +10 | -0.05 (6) | -177 |
| 05:00 | -0.30 (2) | -12 | +1.22 (1) | +70 | -0.77 (2) | -394 |
| 06:00 | +2.16 (3) | +148 |  |  | -0.35 (6) | -600 |
| 07:00 | -0.33 (2) | -13 | -0.22 (2) | +5 | -0.46 (4) | -452 |
| 08:00 | +0.09 (21) | +7 | -0.49 (7) | -150 | +0.05 (6) | +643 |
| 09:00 | +0.22 (25) | +118 | +0.74 (12) | +557 | -0.17 (14) | -1,103 |
| 10:00 | -0.35 (21) | -89 | -0.14 (11) | -5 | -0.50 (6) | -1,284 |
| 11:00 | +0.07 (2) | +2 | -1.01 (3) | -182 | +0.03 (5) | -920 |
| 12:00 | -0.19 (2) | -13 |  |  |  |  |
| 13:00 | +0.74 (7) | +43 | +0.20 (10) | +40 | +0.42 (3) | +421 |
| 14:00 | +0.02 (10) | +13 | -0.02 (6) | -26 | -0.01 (6) | -339 |
| 15:00 | -0.44 (3) | -30 | +0.54 (3) | +31 | -0.45 (4) | -124 |

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
| ict_turtle_soup |  | [-0.37 (7)] | -0.10 (10) | [+0.40 (5)] | -0.07 (22) |
| ict_ote |  | +0.02 (16) | -0.44 (13) | [+0.27 (9)] | -0.08 (38) |
| dtfx_close_origin | [-0.11 (5)] | [+0.43 (5)] | [-1.00 (4)] | [+0.21 (4)] | -0.09 (18) |
| zone_confluence | [+0.82 (1)] | [-1.00 (1)] |  |  | [-0.09 (2)] |
| smc_ifvg | +0.04 (10) | [-0.74 (7)] | +0.00 (10) | [-1.03 (1)] | -0.21 (28) |
| dtfx_wick_fib | [-0.02 (9)] | -0.39 (13) | [-0.34 (9)] | [-0.03 (5)] | -0.24 (36) |
| ict_2022 |  | [-0.40 (5)] | [-0.51 (3)] |  | [-0.44 (8)] |
| smc_displacement | [-1.00 (3)] | [+0.00 (2)] | [-1.00 (1)] |  | [-0.67 (6)] |
| macd_cross | [-0.15 (1)] | [-1.00 (2)] | [-1.00 (3)] |  | [-0.86 (6)] |
| ict_fvg_sweep |  |  | [-1.02 (1)] |  | [-1.02 (1)] |

## 5. Per book: setup × instrument × timeframe

### C10 afternoon

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| c10_afternoon | NDQ | — | n/a | 6 | 67% | **+0.41** | — | +68 | +53 | -71 |

### EMA21 + RSI 55

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| ema21_rsi55 | XAUUSD | — | n/a | 27 | 30% | **+0.13** | — | +80 | +29 | -8 |
| ema21_rsi55 | US30 | — | n/a | 21 | 29% | **-0.26** | — | -1,726 | +104 | -157 |

### Gold breakout

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| gold_breakout | XAUUSD | — | n/a | 13 | 46% | **+0.18** | — | +93 | +49 | -28 |

### Gold H1 trend

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| astra_h1_vol_trend | XAUUSD | — | n/a | 4 | 50% | **+0.75** | — | +100 | +55 | -5 |

### Playbook

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| dtfx_close_fib | US30 | 15m | aligned | 9 | 56% | **+0.42** | — | +394 | +239 | -200 |
| trend_breakout | NDQ | 15m | aligned | 1 | 100% | **+3.75** | — | +226 | +226 | — |
| smc_mss | NDQ | 5m | aligned | 2 | 50% | **+2.08** | — | +225 | +230 | -5 |
| trend_breakout | US30 | 15m | aligned | 1 | 100% | **+0.77** | — | +179 | +179 | — |
| dtfx_close_fib | US30 | 3m | aligned | 1 | 100% | **+0.99** | — | +178 | +178 | — |
| ict_amd | US30 | 5m | aligned | 1 | 100% | **+1.52** | — | +151 | +151 | — |
| dtfx_wick_fib | NDQ | 15m | aligned | 14 | 57% | **-0.09** | — | +75 | +46 | -49 |
| ict_amd | US30 | 3m | aligned | 4 | 50% | **-0.08** | — | +71 | +151 | -116 |
| smc_mss | XAUUSD | 5m | aligned | 3 | 100% | **+0.71** | — | +32 | +11 | — |
| ict_turtle_soup | XAUUSD | 15m | aligned | 5 | 60% | **+0.33** | — | +26 | +13 | -7 |
| smc_mss | XAUUSD | 3m | aligned | 19 | 47% | **-0.01** | — | +24 | +12 | -8 |
| smc_choch | XAUUSD | 3m | aligned | 1 | 100% | **+1.16** | — | +19 | +19 | — |
| ict_amd | NDQ | 5m | aligned | 3 | 33% | **+0.16** | — | +17 | +73 | -28 |
| ict_silver_bullet | XAUUSD | 5m | aligned | 2 | 100% | **+0.58** | — | +13 | +6 | — |
| dtfx_close_fib | XAUUSD | 3m | aligned | 3 | 67% | **-0.20** | — | +0 | +4 | -8 |
| dtfx_wick_fib | NDQ | 5m | aligned | 2 | 50% | **+0.00** | — | -3 | +28 | -31 |
| ict_turtle_soup | XAUUSD | 3m | aligned | 2 | 50% | **-0.05** | — | -6 | +2 | -7 |
| ict_turtle_soup | XAUUSD | 5m | aligned | 7 | 43% | **-0.10** | — | -9 | +10 | -10 |
| dtfx_wick_fib | XAUUSD | 5m | aligned | 1 | 0% | **-0.87** | — | -10 | — | -10 |
| smc_bos_retest | XAUUSD | 15m | aligned | 1 | 0% | **-1.00** | — | -12 | — | -12 |
| smc_ifvg | XAUUSD | 15m | aligned | 4 | 50% | **-0.12** | — | -23 | +4 | -15 |
| ict_2022 | XAUUSD | 3m | aligned | 7 | 29% | **-0.58** | — | -35 | +2 | -8 |
| smc_displacement | XAUUSD | 3m | aligned | 5 | 0% | **-1.00** | — | -42 | — | -8 |
| dtfx_wick_fib | XAUUSD | 3m | aligned | 7 | 14% | **-0.79** | — | -44 | +2 | -8 |
| sr_rejection | NDQ | 30m | aligned | 1 | 0% | **-1.00** | — | -46 | — | -46 |
| ict_ote | NDQ | 3m | aligned | 1 | 0% | **-1.00** | — | -52 | — | -52 |
| smc_bos_retest | XAUUSD | 5m | aligned | 12 | 42% | **-0.21** | — | -55 | +8 | -13 |
| dtfx_close_origin | NDQ | 5m | aligned | 3 | 33% | **-0.22** | — | -83 | +6 | -44 |
| macd_cross | NDQ | 5m | aligned | 4 | 0% | **-0.79** | — | -182 | — | -46 |
| dtfx_wick_fib | US30 | 15m | aligned | 1 | 0% | **-1.00** | — | -419 | — | -419 |
| sr_rejection | US30 | 30m | aligned | 4 | 0% | **-1.00** | — | -550 | — | -137 |

### Playbook, all hours

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| dtfx_close_fib | US30 | 3m | aligned | 2 | 100% | **+0.97** | — | +328 | +164 | — |
| dtfx_close_fib | US30 | 15m | aligned | 6 | 67% | **+0.55** | — | +305 | +255 | -357 |
| smc_mss | NDQ | 5m | aligned | 2 | 50% | **+2.08** | — | +225 | +230 | -5 |
| dtfx_wick_fib | NDQ | 15m | aligned | 4 | 75% | **+0.40** | — | +190 | +85 | -65 |
| trend_breakout | NDQ | 15m | aligned | 2 | 50% | **+1.37** | — | +161 | +226 | -65 |
| dtfx_close_fib_brk | US30 | 3m | aligned | 1 | 100% | **+0.92** | — | +133 | +133 | — |
| ict_turtle_soup | XAUUSD | 15m | aligned | 1 | 100% | **+1.89** | — | +28 | +28 | — |
| smc_mss | XAUUSD | 5m | aligned | 2 | 100% | **+0.84** | — | +26 | +13 | — |
| dtfx_close_fib | XAUUSD | 3m | aligned | 1 | 100% | **+1.64** | — | +18 | +18 | — |
| ict_silver_bullet | XAUUSD | 5m | aligned | 2 | 100% | **+0.57** | — | +13 | +6 | — |
| smc_mss | XAUUSD | 3m | aligned | 2 | 50% | **+0.29** | — | +9 | +12 | -3 |
| smc_bos_retest | XAUUSD | 5m | aligned | 1 | 0% | **-0.11** | — | -2 | — | -2 |
| ict_2022 | XAUUSD | 3m | aligned | 1 | 0% | **-1.00** | — | -9 | — | -9 |
| dtfx_wick_fib | XAUUSD | 5m | aligned | 1 | 0% | **-0.87** | — | -10 | — | -10 |
| ict_amd | NDQ | 5m | aligned | 1 | 0% | **-0.29** | — | -10 | — | -10 |
| smc_bos_retest | XAUUSD | 15m | aligned | 1 | 0% | **-1.00** | — | -14 | — | -14 |
| ict_turtle_soup | XAUUSD | 5m | aligned | 1 | 0% | **-1.00** | — | -16 | — | -16 |
| ict_ote | NDQ | 3m | aligned | 1 | 0% | **-1.00** | — | -52 | — | -52 |
| dtfx_close_origin | NDQ | 5m | aligned | 8 | 50% | **-0.16** | — | -104 | +9 | -35 |
| trend_breakout | US30 | 15m | aligned | 1 | 0% | **-1.00** | — | -118 | — | -118 |
| macd_cross | US30 | 3m | aligned | 1 | 0% | **-1.00** | — | -224 | — | -224 |
| sr_rejection | US30 | 30m | aligned | 1 | 0% | **-1.00** | — | -574 | — | -574 |

### Playbook, no bias rule

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| dtfx_close_fib | US30 | 15m | counter | 2 | 50% | **+0.28** | — | +399 | +573 | -173 |
| dtfx_close_fib | US30 | 3m | aligned | 2 | 100% | **+0.97** | — | +328 | +164 | — |
| dtfx_close_fib | US30 | 15m | aligned | 4 | 75% | **+0.79** | — | +269 | +252 | -486 |
| smc_mss | NDQ | 5m | aligned | 1 | 100% | **+4.20** | — | +230 | +230 | — |
| ict_amd | US30 | 3m | aligned | 1 | 100% | **+1.47** | — | +186 | +186 | — |
| trend_breakout | US30 | 15m | aligned | 1 | 100% | **+0.77** | — | +179 | +179 | — |
| sr_rejection | US30 | 30m | neutral | 2 | 50% | **+0.52** | — | +171 | +281 | -111 |
| dtfx_close_fib | US30 | 3m | neutral | 1 | 100% | **+0.77** | — | +115 | +115 | — |
| ict_ote | NDQ | 3m | counter | 2 | 50% | **+0.81** | — | +90 | +99 | -9 |
| smc_displacement | NDQ | 5m | counter | 1 | 100% | **+1.00** | — | +65 | +65 | — |
| dtfx_wick_fib | US30 | 3m | neutral | 1 | 100% | **+0.60** | — | +45 | +45 | — |
| ict_amd | NDQ | 3m | counter | 1 | 100% | **+0.55** | — | +44 | +44 | — |
| smc_bos_retest | XAUUSD | 15m | aligned | 2 | 100% | **+0.98** | — | +34 | +17 | — |
| ict_turtle_soup | XAUUSD | 15m | aligned | 1 | 100% | **+1.89** | — | +28 | +28 | — |
| smc_mss | XAUUSD | 5m | aligned | 2 | 100% | **+0.84** | — | +26 | +13 | — |
| smc_bos_retest | XAUUSD | 5m | counter | 1 | 100% | **+1.45** | — | +26 | +26 | — |
| smc_mss | XAUUSD | 3m | aligned | 3 | 67% | **+0.51** | — | +20 | +12 | -3 |
| ict_amd | NDQ | 5m | counter | 2 | 50% | **-0.16** | — | +14 | +80 | -67 |
| smc_bos_retest | XAUUSD | 5m | aligned | 4 | 25% | **+0.14** | — | +13 | +31 | -6 |
| ict_turtle_soup | XAUUSD | 5m | aligned | 1 | 100% | **+0.57** | — | +11 | +11 | — |
| dtfx_wick_fib | XAUUSD | 3m | aligned | 1 | 100% | **+1.36** | — | +11 | +11 | — |
| ict_silver_bullet | XAUUSD | 5m | aligned | 2 | 100% | **+0.48** | — | +9 | +4 | — |
| dtfx_wick_fib | NDQ | 5m | neutral | 1 | 100% | **+0.11** | — | +7 | +7 | — |
| dtfx_close_fib | XAUUSD | 3m | counter | 1 | 100% | **+0.21** | — | +5 | +5 | — |
| ict_turtle_soup | XAUUSD | 5m | counter | 2 | 50% | **+0.35** | — | -3 | +23 | -26 |
| ict_2022 | XAUUSD | 3m | aligned | 2 | 50% | **-0.23** | — | -4 | +5 | -9 |
| dtfx_close_origin | NDQ | 5m | counter | 9 | 44% | **-0.10** | — | -7 | +39 | -32 |
| dtfx_wick_fib | XAUUSD | 5m | aligned | 1 | 0% | **-0.87** | — | -10 | — | -10 |
| ict_amd | NDQ | 5m | aligned | 1 | 0% | **-0.29** | — | -10 | — | -10 |
| dtfx_close_fib | XAUUSD | 3m | neutral | 1 | 0% | **-1.00** | — | -14 | — | -14 |
| dtfx_wick_fib | XAUUSD | 5m | neutral | 1 | 0% | **-1.00** | — | -14 | — | -14 |
| smc_mss | XAUUSD | 3m | neutral | 4 | 0% | **-0.57** | — | -27 | — | -7 |
| zone_confluence | NDQ | 3m | aligned | 1 | 0% | **-1.00** | — | -33 | — | -33 |
| smc_mss | XAUUSD | 5m | neutral | 3 | 0% | **-1.00** | — | -37 | — | -12 |
| dtfx_wick_fib | NDQ | 5m | counter | 1 | 0% | **-0.50** | — | -42 | — | -42 |
| ict_ote | NDQ | 3m | aligned | 1 | 0% | **-1.00** | — | -52 | — | -52 |
| ict_turtle_soup | XAUUSD | 15m | neutral | 5 | 20% | **-0.76** | — | -55 | +2 | -14 |
| trend_breakout | NDQ | 15m | aligned | 1 | 0% | **-1.00** | — | -91 | — | -91 |
| dtfx_close_origin | NDQ | 5m | aligned | 5 | 40% | **-0.23** | — | -110 | +7 | -41 |
| smc_mss | NDQ | 5m | counter | 2 | 0% | **-1.00** | — | -205 | — | -103 |
| sr_rejection | US30 | 30m | counter | 1 | 0% | **-1.00** | — | -351 | — | -351 |
| dtfx_wick_fib | US30 | 15m | aligned | 1 | 0% | **-1.00** | — | -419 | — | -419 |
| dtfx_wick_fib | US30 | 15m | counter | 1 | 0% | **-1.00** | — | -474 | — | -474 |

### Playbook + no bias, all hours

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| ict_amd | NDQ | 3m | aligned | 1 | 100% | **+2.65** | — | +330 | +330 | — |
| ict_amd | US30 | 3m | aligned | 1 | 100% | **+1.47** | — | +185 | +185 | — |
| dtfx_close_fib_brk | US30 | 3m | aligned | 1 | 100% | **+0.92** | — | +133 | +133 | — |
| dtfx_close_fib | US30 | 3m | neutral | 1 | 100% | **+0.77** | — | +115 | +115 | — |
| ict_amd | NDQ | 5m | counter | 1 | 100% | **+0.69** | — | +80 | +80 | — |
| smc_displacement | NDQ | 5m | counter | 1 | 100% | **+1.00** | — | +65 | +65 | — |
| trend_breakout | US30 | 15m | aligned | 2 | 50% | **-0.12** | — | +62 | +179 | -118 |
| dtfx_close_origin | NDQ | 5m | counter | 5 | 60% | **+0.14** | — | +48 | +39 | -35 |
| dtfx_wick_fib | US30 | 3m | neutral | 1 | 100% | **+0.60** | — | +45 | +45 | — |
| ict_amd | NDQ | 3m | counter | 1 | 100% | **+0.55** | — | +44 | +44 | — |
| ict_ote | NDQ | 3m | counter | 2 | 50% | **+0.76** | — | +34 | +43 | -9 |
| smc_mss | XAUUSD | 5m | aligned | 2 | 100% | **+0.84** | — | +26 | +13 | — |
| smc_mss | XAUUSD | 3m | aligned | 1 | 100% | **+0.70** | — | +12 | +12 | — |
| dtfx_wick_fib | NDQ | 5m | neutral | 1 | 100% | **+0.11** | — | +7 | +7 | — |
| dtfx_close_fib | XAUUSD | 3m | counter | 1 | 100% | **+0.21** | — | +5 | +5 | — |
| ict_turtle_soup | XAUUSD | 15m | neutral | 1 | 100% | **+0.21** | — | +2 | +2 | — |
| dtfx_wick_fib | XAUUSD | 5m | counter | 1 | 0% | **-0.21** | — | -7 | — | -7 |
| dtfx_close_fib | XAUUSD | 3m | neutral | 3 | 67% | **-0.26** | — | -9 | +2 | -14 |
| zone_confluence | NDQ | 3m | aligned | 2 | 50% | **-0.09** | — | -14 | +19 | -33 |
| smc_mss | XAUUSD | 3m | neutral | 3 | 0% | **-0.37** | — | -16 | — | -5 |
| dtfx_wick_fib | XAUUSD | 5m | neutral | 3 | 33% | **-0.65** | — | -23 | +2 | -12 |
| dtfx_wick_fib | NDQ | 5m | counter | 1 | 0% | **-0.50** | — | -42 | — | -42 |
| ict_ote | NDQ | 3m | aligned | 1 | 0% | **-1.00** | — | -52 | — | -52 |
| dtfx_close_origin | NDQ | 5m | aligned | 1 | 0% | **-1.00** | — | -86 | — | -86 |
| macd_cross | US30 | 3m | counter | 1 | 0% | **-1.00** | — | -132 | — | -132 |
| trend_breakout | NDQ | 15m | aligned | 2 | 0% | **-1.00** | — | -156 | — | -78 |
| dtfx_close_fib | US30 | 15m | counter | 2 | 0% | **-0.50** | — | -173 | — | -87 |
| smc_mss | NDQ | 5m | counter | 2 | 0% | **-0.94** | — | -193 | — | -96 |
| dtfx_wick_fib | US30 | 15m | aligned | 1 | 0% | **-1.00** | — | -419 | — | -419 |
| dtfx_wick_fib | US30 | 15m | counter | 1 | 0% | **-1.00** | — | -474 | — | -474 |
| sr_rejection | US30 | 30m | aligned | 1 | 0% | **-1.00** | — | -574 | — | -574 |

### Practice account

| setup | instrument | tf | bias | trades | win | avg R | 95% range | net pips | avg win pips | avg loss pips |
|---|---|---|---|---|---|---|---|---|---|---|
| sr_rejection | US30 | 5m | aligned | 29 | 59% | **+0.21** | — | +158 | +70 | -86 |
| c10_afternoon | NDQ | — | n/a | 5 | 80% | **+0.78** | — | +108 | +57 | -122 |
| smc_ifvg | NDQ | 15m | aligned | 3 | 67% | **+0.06** | — | +62 | +63 | -64 |
| sr_rejection | NDQ | 5m | aligned | 18 | 67% | **+0.19** | — | +60 | +14 | -19 |
| smc_ifvg | NDQ | 5m | aligned | 3 | 100% | **+0.71** | — | +40 | +13 | — |
| ict_ote | XAUUSD | 5m | aligned | 8 | 62% | **+0.19** | — | +4 | +6 | -9 |
| smc_ifvg | XAUUSD | 5m | aligned | 12 | 33% | **-0.31** | — | -10 | +5 | -4 |
| sr_rejection | XAUUSD | 15m | aligned | 7 | 43% | **-0.23** | — | -12 | +4 | -6 |
| smc_ifvg | XAUUSD | 15m | aligned | 2 | 50% | **+0.09** | — | -13 | +5 | -18 |
| sr_rejection | NDQ | 15m | aligned | 4 | 50% | **-0.16** | — | -21 | +30 | -41 |
| ict_ote | XAUUSD | 15m | aligned | 5 | 20% | **-0.63** | — | -56 | +3 | -15 |
| ict_fvg_sweep | US30 | 5m | aligned | 1 | 0% | **-1.02** | — | -104 | — | -104 |
| ict_ote | NDQ | 5m | aligned | 13 | 46% | **-0.15** | — | -116 | +17 | -31 |
| ict_ote | NDQ | 15m | aligned | 5 | 40% | **-0.24** | — | -150 | +45 | -80 |
| smc_ifvg | US30 | 5m | aligned | 4 | 0% | **-1.02** | — | -226 | — | -56 |
| ict_ote | US30 | 15m | aligned | 3 | 33% | **-0.15** | — | -391 | +146 | -269 |
| sr_rejection | US30 | 15m | aligned | 5 | 20% | **-0.41** | — | -464 | +65 | -132 |

