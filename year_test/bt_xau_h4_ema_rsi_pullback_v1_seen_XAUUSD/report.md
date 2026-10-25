# xau_h4_ema_rsi_pullback_v1 (XAUUSD, code 6d02aa2232cf, engine 38440164bbc2, run 20261025-163508-461b) on seen

Trades 669, win 35%, avg -0.149R (95% -0.233 … -0.064), 2× costs -0.217R, halves -0.157 / -0.142 (329 / 340 trades, split 2023-11-17), exact coin flip -0.083R, max drawdown 112.5R

Coin-flip edge (real − its coin twin, per trade) -0.066R (95% -0.147 … +0.014).

Random timing (same side, same time of day, random other days, same stop % and exits): -0.086R. Timing edge (real − random) -0.064R (95% -0.152 … +0.024); twins found for 100% of trades (twins obey the rule's entry window, news blackout, spread cap and Friday flat).

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

Funnel: signals 1856 → not busy 1132 → filled 1131 → in window 1067 → no news 1065 → under daily cap 669 → risk ok 669 → taken 669

| year | trades | avg R |
|---|---|---|
| 2021 | 115 | -0.177 |
| 2022 | 115 | -0.210 |
| 2023 | 112 | -0.120 |
| 2024 | 111 | -0.203 |
| 2025 | 121 | -0.094 |
| 2026 | 95 | -0.085 |

| exit | trades | avg R |
|---|---|---|
| data_gap | 18 | +0.195 |
| friday_flat | 54 | +0.254 |
| max_hold | 91 | +0.463 |
| stop | 385 | -1.030 |
| target | 121 | +1.960 |

Variant no_h4_ema_regime: 1418 trades, avg -0.137R
Variant no_sr_room_filter: 686 trades, avg -0.146R
Engine 38440164bbc2 (fill-minute targets, open-first ordering, market slippage 10% of spread; 2× costs = every half-spread and slippage plus the financing charged again; halves split at the period's calendar midpoint).
Look-ahead audit: 20 cuts, 33 signals in the day before each cut compared both ways (missing, changed, or signalled on cut data but skipped by the full run), 0 failed.
