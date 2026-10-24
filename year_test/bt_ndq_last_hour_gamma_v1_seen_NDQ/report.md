# ndq_last_hour_gamma_v1 (NDQ, code ae92ff558bb9, engine e59d49c4203e, run 20261023-204716-053f) on seen

Trades 416, win 49%, avg +0.065R (95% -0.044 … +0.166), 2× costs +0.050R, halves +0.138 / -0.007, exact coin flip -0.035R, max drawdown 19.6R

Coin-flip edge (real − its coin twin, per trade) +0.100R (95% +0.003 … +0.194).

Random timing (same side, same time of day, random other days, same stop % and exits): -0.006R. Timing edge (real − random) +0.071R (95% -0.041 … +0.173).

| gate | |
|---|---|
| ≥ 100 trades | yes |
| avg R > 0 | yes |
| 95% range above 0 | no |
| positive at 2× costs | yes |
| positive in both halves | no |
| beats the coin flip (95% above 0) | yes |
| beats random timing (95% above 0) | no |
| PASS | no |
| beats its variants | no |

Funnel: signals 416 → not busy 416 → filled 416 → in window 416 → no news 416 → under daily cap 416 → risk ok 416 → taken 416

| year | trades | avg R |
|---|---|---|
| 2021 | 71 | +0.023 |
| 2022 | 80 | +0.246 |
| 2023 | 81 | +0.099 |
| 2024 | 64 | -0.126 |
| 2025 | 66 | -0.048 |
| 2026 | 54 | +0.167 |

| exit | trades | avg R |
|---|---|---|
| flat | 193 | +0.312 |
| stop | 152 | -1.012 |
| target | 71 | +1.700 |

Variant no_bimodal_agreement: 664 trades, avg +0.053R
Variant no_magnitude_filter: 506 trades, avg +0.092R
Engine e59d49c4203e (fill-minute targets, open-first ordering, market slippage 10% of spread).
Look-ahead audit: 10 signals re-run on truncated data (time, side, stop, target, entry price and risk limits compared), 0 changed.
