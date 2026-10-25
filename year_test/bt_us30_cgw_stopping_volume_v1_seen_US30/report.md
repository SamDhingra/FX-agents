# us30_cgw_stopping_volume_v1 (US30, code f8c92f7cb0fa, engine 38440164bbc2, run 20261025-163603-8cba) on seen

Trades 520, win 39%, avg -0.053R (95% -0.154 … +0.053), 2× costs -0.080R, halves -0.133 / +0.026 (259 / 261 trades, split 2023-11-17), exact coin flip -0.019R, max drawdown 48.3R

Coin-flip edge (real − its coin twin, per trade) -0.034R (95% -0.123 … +0.062).

Random timing (same side, same time of day, random other days, same stop % and exits): -0.040R. Timing edge (real − random) -0.013R (95% -0.117 … +0.097); twins found for 100% of trades (twins obey the rule's entry window, news blackout, spread cap and Friday flat).

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

Funnel: signals 1015 → not busy 857 → filled 857 → in window 857 → no news 857 → under daily cap 520 → risk ok 520 → taken 520

| year | trades | avg R |
|---|---|---|
| 2021 | 93 | -0.098 |
| 2022 | 96 | -0.011 |
| 2023 | 79 | -0.309 |
| 2024 | 95 | +0.125 |
| 2025 | 94 | -0.132 |
| 2026 | 63 | +0.121 |

| exit | trades | avg R |
|---|---|---|
| data_gap | 1 | +0.065 |
| flat | 108 | +0.209 |
| stop | 270 | -1.013 |
| target | 141 | +1.584 |

Variant no_volume_climax: 1436 trades, avg +0.014R
Variant no_absorption_filter: 706 trades, avg -0.078R
Engine 38440164bbc2 (fill-minute targets, open-first ordering, market slippage 10% of spread; 2× costs = every half-spread and slippage plus the financing charged again; halves split at the period's calendar midpoint).
Look-ahead audit: 20 cuts, 31 signals in the day before each cut compared both ways (missing, changed, or signalled on cut data but skipped by the full run), 0 failed.
