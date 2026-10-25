# us30_adr_exhaustion_fade_v1 (US30, code 47c133d94170, engine 38440164bbc2, run 20261025-163327-4714) on seen

Trades 522, win 43%, avg +0.009R (95% -0.086 … +0.106), 2× costs -0.017R, halves -0.043 / +0.057 (248 / 274 trades, split 2023-11-17), exact coin flip -0.024R, max drawdown 17.3R

Coin-flip edge (real − its coin twin, per trade) +0.033R (95% -0.060 … +0.123).

Random timing (same side, same time of day, random other days, same stop % and exits): -0.018R. Timing edge (real − random) +0.028R (95% -0.071 … +0.130); twins found for 100% of trades (twins obey the rule's entry window, news blackout, spread cap and Friday flat).

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

Funnel: signals 1143 → not busy 846 → filled 845 → in window 845 → no news 845 → under daily cap 522 → risk ok 522 → taken 522

| year | trades | avg R |
|---|---|---|
| 2021 | 77 | -0.087 |
| 2022 | 85 | -0.050 |
| 2023 | 94 | +0.011 |
| 2024 | 94 | +0.092 |
| 2025 | 94 | -0.068 |
| 2026 | 78 | +0.162 |

| exit | trades | avg R |
|---|---|---|
| data_gap | 2 | -0.430 |
| flat | 111 | +0.117 |
| stop | 246 | -1.014 |
| target | 163 | +1.485 |

Variant no_adr_exhaustion: 769 trades, avg +0.008R
Variant no_rsi_filter: 551 trades, avg -0.008R
Engine 38440164bbc2 (fill-minute targets, open-first ordering, market slippage 10% of spread; 2× costs = every half-spread and slippage plus the financing charged again; halves split at the period's calendar midpoint).
Look-ahead audit: 20 cuts, 28 signals in the day before each cut compared both ways (missing, changed, or signalled on cut data but skipped by the full run), 0 failed.
