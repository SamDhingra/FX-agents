# xau_h4_value_entry_v1 (XAUUSD, code 1780e648587f, engine e59d49c4203e, run 20261025-143512-8ca7) on seen

Trades 325, win 49%, avg +0.037R (95% -0.086 … +0.162), 2× costs -0.019R, halves +0.063 / +0.010, exact coin flip -0.029R, max drawdown 12.5R

Coin-flip edge (real − its coin twin, per trade) +0.066R (95% -0.044 … +0.178).

Random timing (same side, same time of day, random other days, same stop % and exits): -0.065R. Timing edge (real − random) +0.102R (95% -0.030 … +0.236).

| gate | |
|---|---|
| ≥ 100 trades | yes |
| avg R > 0 | yes |
| 95% range above 0 | no |
| positive at 2× costs | no |
| positive in both halves | yes |
| beats the coin flip (95% above 0) | no |
| beats random timing (95% above 0) | no |
| PASS | no |
| beats its variants | no |

Funnel: signals 528 → not busy 362 → filled 362 → in window 362 → no news 362 → under daily cap 359 → risk ok 325 → taken 325

| year | trades | avg R |
|---|---|---|
| 2021 | 47 | +0.039 |
| 2022 | 68 | +0.062 |
| 2023 | 51 | +0.114 |
| 2024 | 58 | +0.082 |
| 2025 | 53 | +0.021 |
| 2026 | 48 | -0.121 |

| exit | trades | avg R |
|---|---|---|
| end | 1 | +0.699 |
| friday_flat | 90 | +0.530 |
| max_hold | 103 | +0.963 |
| stop | 131 | -1.036 |

Variant no_slow_regime: 362 trades, avg +0.065R
Engine e59d49c4203e (fill-minute targets, open-first ordering, market slippage 10% of spread).
Look-ahead audit: 10 signals re-run on truncated data (time, side, stop, target, entry price and risk limits compared), 0 changed.
