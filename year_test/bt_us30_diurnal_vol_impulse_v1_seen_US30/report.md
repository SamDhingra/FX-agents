# us30_diurnal_vol_impulse_v1 (US30, code 95718c207344, engine e59d49c4203e, run 20261023-204731-cdcd) on seen

Trades 148, win 36%, avg -0.009R (95% -0.211 … +0.188), 2× costs -0.030R, halves +0.019 / -0.037, exact coin flip +0.054R, max drawdown 20.0R

Coin-flip edge (real − its coin twin, per trade) -0.063R (95% -0.265 … +0.131).

Random timing (same side, same time of day, random other days, same stop % and exits): -0.016R. Timing edge (real − random) +0.007R (95% -0.201 … +0.216).

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
| beats its variants | no |

Funnel: signals 148 → not busy 148 → filled 148 → in window 148 → no news 148 → under daily cap 148 → risk ok 148 → taken 148

| year | trades | avg R |
|---|---|---|
| 2021 | 32 | +0.134 |
| 2022 | 19 | -0.136 |
| 2023 | 18 | -0.098 |
| 2024 | 36 | -0.140 |
| 2025 | 24 | +0.309 |
| 2026 | 19 | -0.194 |

| exit | trades | avg R |
|---|---|---|
| flat | 19 | +0.617 |
| stop | 89 | -1.014 |
| target | 40 | +1.929 |

Variant no_diurnal_vol_filter: 544 trades, avg +0.029R
Variant no_efficiency_filter: 214 trades, avg -0.002R
Engine e59d49c4203e (fill-minute targets, open-first ordering, market slippage 10% of spread).
Look-ahead audit: 10 signals re-run on truncated data (time, side, stop, target, entry price and risk limits compared), 0 changed.
