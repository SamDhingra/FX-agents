# gpt_c10_afternoon_continuation_v2 (NDQ, code 8d23c814cc28, run 20261020-235106-f5b2) on seen

Trades 251, win 55%, avg +0.258R (95% +0.115 … +0.410), 2× costs +0.243R, halves +0.265 / +0.251, exact coin flip -0.015R, max drawdown 6.1R

Random timing (same side, same time of day, random other days, same stop % and hold): -0.033R. Timing edge (real − random) +0.291R (95% +0.144 … +0.444).

| gate | |
|---|---|
| ≥ 100 trades | yes |
| avg R > 0 | yes |
| 95% range above 0 | yes |
| positive at 2× costs | yes |
| positive in both halves | yes |
| beats the coin flip | yes |
| beats random timing | yes |
| PASS | yes |

Funnel: signals 256 → not busy 256 → filled 252 → in window 252 → no news 252 → under daily cap 252 → risk ok 251 → taken 251

| year | trades | avg R |
|---|---|---|
| 2021 | 47 | +0.041 |
| 2022 | 47 | +0.366 |
| 2023 | 46 | +0.439 |
| 2024 | 42 | +0.227 |
| 2025 | 36 | +0.284 |
| 2026 | 33 | +0.172 |

| exit | trades | avg R |
|---|---|---|
| data_gap | 3 | +0.102 |
| flat | 106 | +0.552 |
| stop | 92 | -1.012 |
| target | 50 | +1.981 |

Look-ahead audit: 10 signals re-run on truncated data, 0 changed.
