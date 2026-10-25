# ndq_fresh_cash_edge_v1 (NDQ, code f8a6173c14da, engine e59d49c4203e, run 20261025-143409-c205) on seen

Trades 132, win 36%, avg -0.031R (95% -0.246 … +0.192), 2× costs -0.042R, halves +0.014 / -0.076, exact coin flip -0.007R, max drawdown 19.4R

Coin-flip edge (real − its coin twin, per trade) -0.024R (95% -0.214 … +0.167).

Random timing (same side, same time of day, random other days, same stop % and exits): -0.016R. Timing edge (real − random) -0.015R (95% -0.252 … +0.226).

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

Funnel: signals 135 → not busy 135 → filled 135 → in window 135 → no news 135 → under daily cap 135 → risk ok 132 → taken 132

| year | trades | avg R |
|---|---|---|
| 2021 | 20 | -0.239 |
| 2022 | 29 | +0.149 |
| 2023 | 32 | +0.030 |
| 2024 | 22 | +0.522 |
| 2025 | 20 | -0.379 |
| 2026 | 9 | -0.946 |

| exit | trades | avg R |
|---|---|---|
| data_gap | 1 | -0.589 |
| flat | 22 | +0.181 |
| stop | 72 | -1.012 |
| target | 37 | +1.766 |

Variant no_rsi_state: 173 trades, avg -0.003R
Variant allow_used_edge: 333 trades, avg -0.018R
Engine e59d49c4203e (fill-minute targets, open-first ordering, market slippage 10% of spread).
Look-ahead audit: 10 signals re-run on truncated data (time, side, stop, target, entry price and risk limits compared), 0 changed.
