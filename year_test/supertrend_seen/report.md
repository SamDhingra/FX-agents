# SuperTrend + EMA + RSI — seen (2021-01-01 → 2026-10-01)

Registered Nov 2 2026 before running (research/supertrend/PREREGISTRATION_2026-11-02.md). SuperTrend(10, 3) + EMA 200 + RSI(14) 50–70 / 30–50, 15-minute candles, entries 03:00–15:30 NY at the signal candle's close (real bid/ask), stop and trail at the SuperTrend line, exit on a flip or 15:50. NDQ + gold + US30 pooled.

Gates: ≥ 100 trades, avg R > 0, 95% range above 0, avg R > 0 at 2× costs, both halves (split 2023-11-17) > 0, and better than the random-timing control.

| rule | verdict | trades | win | avg R | 95% range | 2× costs | halves | random-timing control | spread / risk |
|---|---|---|---|---|---|---|---|---|---|
| st_ema_rsi | no | 9508 | 35% | +0.029 | -0.007 to +0.062 | -0.010 | +0.048 / +0.009 | +0.000 | 3% |
| random-timing control | info | 9508 | 34% | +0.000 | -0.046 to +0.049 | -0.046 | -0.010 / +0.010 | +nan | 3% |

**st_ema_rsi does not pass → the vault is not touched; the idea is closed.**

## Shown, not judged

| rule | verdict | trades | win | avg R | 95% range | 2× costs | halves | random-timing control | spread / risk |
|---|---|---|---|---|---|---|---|---|---|
| SuperTrend flips alone | info | 6751 | 38% | +0.021 | -0.008 to +0.053 | -0.003 | +0.022 / +0.021 | +nan | 2% |
| same entries, RSI exit | info | 12915 | 29% | +0.004 | -0.020 to +0.029 | -0.036 | +0.023 / -0.014 | +nan | 3% |
| 5-minute candles | info | 21574 | 32% | -0.023 | -0.045 to -0.001 | -0.085 | -0.006 / -0.041 | +nan | 5% |
| 1-hour candles | info | 3756 | 43% | -0.015 | -0.049 to +0.019 | -0.034 | +0.008 / -0.038 | +nan | 1% |

### st_ema_rsi by instrument

| rule | verdict | trades | win | avg R | 95% range | 2× costs | halves | random-timing control | spread / risk |
|---|---|---|---|---|---|---|---|---|---|
| NDQ | info | 3242 | 35% | +0.067 | +0.009 to +0.123 | +0.035 | +0.095 / +0.036 | +nan | 2% |
| US30 | info | 3396 | 36% | +0.015 | -0.036 to +0.067 | -0.017 | +0.048 / -0.017 | +nan | 2% |
| XAUUSD | info | 2870 | 35% | +0.003 | -0.052 to +0.058 | -0.054 | -0.004 / +0.010 | +nan | 4% |

### by entry hour (NY)

| hour | trades | avg R |
|---|---|---|
| 03 | 1573 | +0.027 |
| 04 | 1065 | +0.013 |
| 05 | 659 | +0.070 |
| 06 | 506 | +0.089 |
| 07 | 560 | +0.001 |
| 08 | 722 | +0.028 |
| 09 | 1055 | +0.077 |
| 10 | 1255 | +0.036 |
| 11 | 724 | -0.018 |
| 12 | 468 | -0.003 |
| 13 | 402 | +0.034 |
| 14 | 342 | -0.044 |
| 15 | 177 | -0.020 |

Exit reasons: stop 6265, flat 3243
