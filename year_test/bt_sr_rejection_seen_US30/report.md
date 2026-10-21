# sr_rejection (US30, code 212aa643bca6, run 20261021-165017-caae) on seen

Trades 4274, win 42%, avg -0.189R (95% -0.216 … -0.153), 2× costs -0.334R, halves -0.132 / -0.247, exact coin flip -0.181R, max drawdown 812.7R

Random timing (same side, same time of day, random other days, same stop % and hold): -0.166R. Timing edge (real − random) -0.024R (95% -0.054 … +0.010).

| gate | |
|---|---|
| ≥ 100 trades | yes |
| avg R > 0 | no |
| 95% range above 0 | no |
| positive at 2× costs | no |
| positive in both halves | no |
| beats the coin flip | no |
| beats random timing | no |
| PASS | no |
| beats its variants | no |
| no look-ahead | no |

Funnel: signals 8472 → not busy 7934 → filled 7915 → in window 4308 → no news 4274 → under daily cap 4274 → risk ok 4274 → taken 4274

| year | trades | avg R |
|---|---|---|
| 2021 | 802 | -0.160 |
| 2022 | 776 | -0.123 |
| 2023 | 704 | -0.121 |
| 2024 | 700 | -0.229 |
| 2025 | 745 | -0.306 |
| 2026 | 547 | -0.203 |

| exit | trades | avg R |
|---|---|---|
| adjust_stop | 18 | +1.305 |
| data_gap | 1 | +0.833 |
| flat | 62 | +1.063 |
| max_hold | 20 | +1.313 |
| partial_stop | 795 | +0.536 |
| step_stop | 575 | +1.397 |
| stop | 2462 | -1.035 |
| stop_same_bar | 341 | +1.157 |

Variant no_bias: 9709 trades, avg -0.181R
Look-ahead audit: 10 signals re-run on truncated data, 1 changed (e.g. 2026-09-30T13:05:00-04:00).
