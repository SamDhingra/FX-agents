# xau_london_fix_reversion_v1 (XAUUSD, code 97e047e6539c, engine e59d49c4203e, run 20261023-204744-f203) on seen

Trades 126, win 47%, avg +0.000R (95% -0.198 … +0.191), 2× costs -0.044R, halves -0.034 / +0.034, exact coin flip -0.069R, max drawdown 11.4R

Coin-flip edge (real − its coin twin, per trade) +0.070R (95% -0.111 … +0.241).

Random timing (same side, same time of day, random other days, same stop % and exits): -0.054R. Timing edge (real − random) +0.055R (95% -0.146 … +0.248).

| gate | |
|---|---|
| ≥ 100 trades | yes |
| avg R > 0 | yes |
| 95% range above 0 | no |
| positive at 2× costs | no |
| positive in both halves | no |
| beats the coin flip (95% above 0) | no |
| beats random timing (95% above 0) | no |
| PASS | no |
| beats its variants | yes |

Funnel: signals 126 → not busy 126 → filled 126 → in window 126 → no news 126 → under daily cap 126 → risk ok 126 → taken 126

| year | trades | avg R |
|---|---|---|
| 2021 | 18 | +0.238 |
| 2022 | 28 | -0.150 |
| 2023 | 14 | -0.398 |
| 2024 | 19 | +0.148 |
| 2025 | 17 | -0.016 |
| 2026 | 30 | +0.100 |

| exit | trades | avg R |
|---|---|---|
| flat | 43 | +0.412 |
| stop | 58 | -1.017 |
| target | 25 | +1.652 |

Variant no_extension_filter: 317 trades, avg -0.044R
Variant no_rejection_filter: 275 trades, avg -0.082R
Engine e59d49c4203e (fill-minute targets, open-first ordering, market slippage 10% of spread).
Look-ahead audit: 10 signals re-run on truncated data (time, side, stop, target, entry price and risk limits compared), 0 changed.
