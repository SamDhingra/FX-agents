# xau_h1_adr_exhaustion_v1 (XAUUSD, code 4f68ddea4268, engine e59d49c4203e, run 20261025-143429-6108) on seen

Trades 292, win 47%, avg -0.058R (95% -0.111 … -0.004), 2× costs -0.087R, halves -0.054 / -0.062, exact coin flip -0.033R, max drawdown 19.4R

Coin-flip edge (real − its coin twin, per trade) -0.025R (95% -0.080 … +0.030).

Random timing (same side, same time of day, random other days, same stop % and exits): -0.040R. Timing edge (real − random) -0.019R (95% -0.078 … +0.040).

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

Funnel: signals 364 → not busy 364 → filled 364 → in window 364 → no news 364 → under daily cap 364 → risk ok 292 → taken 292

| year | trades | avg R |
|---|---|---|
| 2021 | 40 | -0.015 |
| 2022 | 58 | -0.146 |
| 2023 | 46 | -0.025 |
| 2024 | 52 | -0.016 |
| 2025 | 58 | -0.080 |
| 2026 | 38 | -0.036 |

| exit | trades | avg R |
|---|---|---|
| friday_flat | 57 | +0.033 |
| max_hold | 216 | +0.002 |
| stop | 19 | -1.014 |

Variant no_adr_gate: 531 trades, avg -0.046R
Variant continue_extension: 292 trades, avg -0.003R
Engine e59d49c4203e (fill-minute targets, open-first ordering, market slippage 10% of spread).
Look-ahead audit: 10 signals re-run on truncated data (time, side, stop, target, entry price and risk limits compared), 0 changed.
