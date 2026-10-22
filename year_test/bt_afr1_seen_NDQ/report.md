# afr1 (NDQ, code 2ec8dad9b22d, run 20261021-234117-a76f) on seen

Trades 108, win 35%, avg +0.010R (95% -0.240 … +0.277), 2× costs -0.023R, halves +0.035 / -0.014, exact coin flip -0.002R, max drawdown 13.3R

Random timing (same side, same time of day, random other days, same stop % and hold): -0.054R. Timing edge (real − random) +0.064R (95% -0.184 … +0.330).

| gate | |
|---|---|
| ≥ 100 trades | yes |
| avg R > 0 | yes |
| 95% range above 0 | no |
| positive at 2× costs | no |
| positive in both halves | no |
| beats the coin flip | yes |
| beats random timing | yes |
| PASS | no |
| beats its variants | no |

Funnel: signals 108 → not busy 108 → filled 108 → in window 108 → no news 108 → under daily cap 108 → risk ok 108 → taken 108

| year | trades | avg R |
|---|---|---|
| 2021 | 18 | -0.183 |
| 2022 | 21 | -0.016 |
| 2023 | 24 | +0.046 |
| 2024 | 14 | +0.696 |
| 2025 | 15 | -0.680 |
| 2026 | 16 | +0.256 |

| exit | trades | avg R |
|---|---|---|
| flat | 5 | +0.767 |
| stop | 69 | -1.015 |
| target | 34 | +1.980 |

Variant c10_stop: 118 trades, avg +0.214R
Variant c10_matched: 249 trades, avg +0.280R
Look-ahead audit: 10 signals re-run on truncated data, 0 changed.

## Per eligible day (the 13:00 context armed on 263 days; 0R on days without a trade)

| book | trades | net R per eligible day | total R |
|---|---|---|---|
| afr (afr) | 108 | +0.0043 | +1.12 |
| c10_stop | 118 | +0.0961 | +25.27 |
| c10_matched | 249 | +0.2653 | +69.78 |

AFR − matched C10, per eligible day: -0.2611R (95% week-block -0.4091 … -0.1016); AFR traded 108 of 263 days, C10-matched 249.

| rejection (this book) | count |
|---|---|
| friction > 10% of the stop | 11 |
| early close | 5 |
| morning direction invalidated (day off) | 3 |
| scheduled event | 2 |
| stop too far (> 1.25 × ATR15) | 1 |
