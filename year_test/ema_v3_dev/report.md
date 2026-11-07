# EMA21 round 3: dev (dev_m1, halves split 2025-10-01)

Registered Nov 7 2026 (research/ema_v3/PREREGISTRATION_2026-11-07.md). Long only, entries 02:00–15:30 NY, flat 15:50, exit on the first 15m close below EMA21, resting stop at entry − 3 × ATR (as the live book). R = ATR(14, 15m) at entry (a stop-out ≈ −3R; the live journal's R = this ÷ 3). Real OANDA bid/ask.

`ref` = the original EMA21 + RSI55 (reference). `A_norsi` = the cross without RSI. `B_h1` = the original cross with the last completed 1h candle above its EMA21. **vs random** = average R minus the same-hour, same-half random entries with the same exits.

| instrument | config | trades | win | avg R | 95% range | 99.2% range | 2× costs | halves | random | vs random (95%) | daily vs ref | stop hits | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | ref | 371 | 33% | **+0.095** | -0.158 to +0.384 | -0.252 to +0.503 | -0.018 | +0.049 / +0.145 | -0.033 | +0.128 (-0.139 to +0.418) | — | 3.2% | reference |
| XAUUSD | A_norsi | 1,908 | 25% | **-0.064** | -0.142 to +0.021 | -0.163 to +0.053 | -0.174 | -0.052 / -0.076 | -0.124 | +0.060 (-0.024 to +0.152) | -0.303 | 1.7% | fail: 95% range > 0, 2× costs > 0, both halves > 0, beats random timing, adds to the daily result vs ref |
| XAUUSD | B_h1 | 256 | 36% | **+0.235** | -0.091 to +0.610 | -0.192 to +0.756 | +0.118 | +0.318 / +0.151 | -0.025 | +0.261 (-0.086 to +0.656) | +0.048 | 2.7% | fail: 95% range > 0, beats random timing |
| NDQ | ref | 434 | 31% | **+0.117** | -0.200 to +0.479 | -0.305 to +0.621 | +0.051 | -0.086 / +0.349 | +0.257 | -0.140 (-0.479 to +0.237) | — | 7.4% | reference |
| NDQ | A_norsi | 1,860 | 26% | **+0.021** | -0.098 to +0.154 | -0.134 to +0.195 | -0.047 | +0.003 / +0.041 | +0.315 | -0.294 (-0.421 to -0.158) | -0.022 | 4.7% | fail: 95% range > 0, 2× costs > 0, beats random timing, adds to the daily result vs ref |
| NDQ | B_h1 | 305 | 31% | **+0.114** | -0.260 to +0.550 | -0.369 to +0.749 | +0.042 | -0.373 / +0.712 | +0.262 | -0.148 (-0.528 to +0.296) | -0.031 | 7.2% | fail: 95% range > 0, both halves > 0, beats random timing, adds to the daily result vs ref |
| US30 | ref | 492 | 32% | **+0.257** | -0.094 to +0.680 | -0.207 to +0.831 | +0.165 | +0.572 / -0.036 | +0.167 | +0.089 (-0.294 to +0.533) | — | 9.8% | reference |
| US30 | A_norsi | 2,036 | 24% | **-0.041** | -0.159 to +0.094 | -0.204 to +0.148 | -0.129 | -0.049 / -0.033 | +0.121 | -0.162 (-0.285 to -0.022) | -0.402 | 4.7% | fail: 95% range > 0, 2× costs > 0, both halves > 0, beats random timing, adds to the daily result vs ref |
| US30 | B_h1 | 301 | 31% | **+0.518** | -0.001 to +1.119 | -0.144 to +1.399 | +0.421 | +0.782 / +0.260 | +0.175 | +0.343 (-0.200 to +0.972) | +0.057 | 9.0% | fail: 95% range > 0, beats random timing |

## Information

| instrument | config | trades/day | net pips | avg R in stop units (live journal) | spread R | exits |
|---|---|---|---|---|---|---|
| XAUUSD | ref | 0.71 | +3,153 | +0.032 | 0.114 | ema_exit 302, flat_1550 56, stop 12, closure 1 |
| XAUUSD | A_norsi | 3.66 | -10,104 | -0.021 | 0.110 | ema_exit 1641, flat_1550 224, stop 33, closure 10 |
| XAUUSD | B_h1 | 0.49 | +4,008 | +0.078 | 0.118 | ema_exit 209, flat_1550 39, stop 7, closure 1 |
| NDQ | ref | 0.83 | +1,550 | +0.039 | 0.066 | ema_exit 329, flat_1550 71, stop 32, closure 2 |
| NDQ | A_norsi | 3.56 | +238 | +0.007 | 0.068 | ema_exit 1521, flat_1550 237, stop 88, closure 14 |
| NDQ | B_h1 | 0.58 | +406 | +0.038 | 0.072 | ema_exit 231, flat_1550 50, stop 22, closure 2 |
| US30 | ref | 0.94 | +5,151 | +0.086 | 0.091 | ema_exit 362, flat_1550 79, stop 48, closure 3 |
| US30 | A_norsi | 3.90 | -3,302 | -0.014 | 0.088 | ema_exit 1695, flat_1550 234, stop 95, closure 12 |
| US30 | B_h1 | 0.58 | +3,373 | +0.173 | 0.097 | ema_exit 221, flat_1550 52, stop 27, closure 1 |

Code check, `ref` without the stop (should match the earlier v2 day-long results on dev_m1): XAUUSD 371 trades +0.079R, NDQ 434 trades +0.108R, US30 492 trades +0.286R

**Passed: none.**

Nothing passed: per the registration, EMA21 research stops here.
