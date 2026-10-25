# ndq_pdhl_adr_breakout_v1 (NDQ, code 59d59e69920b, engine 38440164bbc2, run 20261025-163237-64f4) on seen

Trades 307, win 35%, avg -0.130R (95% -0.261 … +0.004), 2× costs -0.156R, halves -0.102 / -0.159 (155 / 152 trades, split 2023-11-17), exact coin flip -0.080R, max drawdown 58.4R

Coin-flip edge (real − its coin twin, per trade) -0.050R (95% -0.164 … +0.065).

Random timing (same side, same time of day, random other days, same stop % and exits): -0.030R. Timing edge (real − random) -0.100R (95% -0.240 … +0.042); twins found for 100% of trades (twins obey the rule's entry window, news blackout, spread cap and Friday flat).

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

Funnel: signals 463 → not busy 408 → filled 408 → in window 398 → no news 398 → under daily cap 307 → risk ok 307 → taken 307

| year | trades | avg R |
|---|---|---|
| 2021 | 47 | -0.268 |
| 2022 | 60 | -0.224 |
| 2023 | 56 | +0.138 |
| 2024 | 49 | -0.574 |
| 2025 | 56 | -0.019 |
| 2026 | 39 | +0.192 |

| exit | trades | avg R |
|---|---|---|
| data_gap | 4 | +0.512 |
| flat | 41 | +0.267 |
| stop | 186 | -1.013 |
| target | 76 | +1.782 |

Variant no_adr_filter: 653 trades, avg -0.112R
Variant no_ema_filter: 333 trades, avg -0.149R
Engine 38440164bbc2 (fill-minute targets, open-first ordering, market slippage 10% of spread; 2× costs = every half-spread and slippage plus the financing charged again; halves split at the period's calendar midpoint).
Look-ahead audit: 20 cuts, 13 signals in the day before each cut compared both ways (missing, changed, or signalled on cut data but skipped by the full run), 0 failed.
