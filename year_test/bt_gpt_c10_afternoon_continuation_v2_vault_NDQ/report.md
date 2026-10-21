# gpt_c10_afternoon_continuation_v2 (NDQ, code 8d23c814cc28, run 20261020-235156-a7e4) on vault

Trades 141, win 47%, avg +0.082R (95% -0.123 … +0.295), 2× costs +0.047R, halves +0.135 / +0.029, exact coin flip -0.125R, max drawdown 10.8R

Random timing (same side, same time of day, random other days, same stop % and hold): -0.074R. Timing edge (real − random) +0.155R (95% -0.060 … +0.378).

| gate | |
|---|---|
| ≥ 100 trades | yes |
| avg R > 0 | yes |
| 95% range above 0 | no |
| positive at 2× costs | yes |
| positive in both halves | yes |
| beats the coin flip | yes |
| beats random timing | yes |
| PASS | no |

Funnel: signals 190 → not busy 190 → filled 188 → in window 188 → no news 188 → under daily cap 188 → risk ok 141 → taken 141

| year | trades | avg R |
|---|---|---|
| 2016 | 15 | +0.566 |
| 2017 | 5 | -0.321 |
| 2018 | 44 | +0.082 |
| 2019 | 36 | -0.056 |
| 2020 | 41 | +0.074 |

| exit | trades | avg R |
|---|---|---|
| data_gap | 2 | +0.414 |
| flat | 44 | +0.665 |
| stop | 69 | -1.015 |
| target | 26 | +1.980 |

Look-ahead audit: 10 signals re-run on truncated data, 0 changed.
