# ndq_clock_flow_v1 (NDQ, code 49cd9af95fb0, engine e59d49c4203e, run 20261023-124912-0b12) on seen

Trades 1460, win 48%, avg -0.005R (95% -0.042 … +0.030), 2× costs -0.015R, halves +0.004 / -0.014, exact coin flip -0.018R, max drawdown 45.8R

Coin-flip edge (real − its coin twin, per trade) +0.013R (95% -0.024 … +0.047).

Random timing (same side, same time of day, random other days, same stop % and exits): -0.029R. Timing edge (real − random) +0.024R (95% -0.018 … +0.064).

| gate | |
|---|---|
| ≥ 100 trades | yes |
| avg R > 0 | no |
| 95% range above 0 | no |
| positive at 2× costs | no |
| positive in both halves | no |
| beats the coin flip (95% above 0) | no |
| beats random timing (95% above 0) | no |
| PASS | no |
| beats its variants | yes |

Funnel: signals 1462 → not busy 1462 → filled 1462 → in window 1462 → no news 1462 → under daily cap 1462 → risk ok 1460 → taken 1460

| year | trades | avg R |
|---|---|---|
| 2021 | 238 | -0.006 |
| 2022 | 257 | +0.030 |
| 2023 | 257 | -0.016 |
| 2024 | 259 | -0.070 |
| 2025 | 256 | +0.028 |
| 2026 | 193 | +0.006 |

| exit | trades | avg R |
|---|---|---|
| flat | 1229 | +0.184 |
| stop | 231 | -1.012 |

Variant previous_half_hour: 1460 trades, avg -0.019R
Engine e59d49c4203e (fill-minute targets, open-first ordering, market slippage 10% of spread).
Look-ahead audit: 10 signals re-run on truncated data (time, side, stop, target, entry price and risk limits compared), 0 changed.
