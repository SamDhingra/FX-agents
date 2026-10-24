# xau_rsi2_comex_session_v1 (XAUUSD, code ce576c3d2753, engine e59d49c4203e, run 20261023-204756-bdac) on seen

Trades 32, win 31%, avg -0.151R (95% -0.639 … +0.353), 2× costs -0.209R, halves +0.234 / -0.537, exact coin flip -0.095R, max drawdown 14.6R

Coin-flip edge (real − its coin twin, per trade) -0.056R (95% -0.469 … +0.357).

Random timing (same side, same time of day, random other days, same stop % and exits): -0.042R. Timing edge (real − random) -0.109R (95% -0.580 … +0.387).

| gate | |
|---|---|
| ≥ 100 trades | no |
| avg R > 0 | no |
| 95% range above 0 | no |
| positive at 2× costs | no |
| positive in both halves | no |
| beats the coin flip (95% above 0) | no |
| beats random timing (95% above 0) | no |
| PASS | no |
| beats its variants | no |

Funnel: signals 32 → not busy 32 → filled 32 → in window 32 → no news 32 → under daily cap 32 → risk ok 32 → taken 32

| year | trades | avg R |
|---|---|---|
| 2021 | 4 | +1.128 |
| 2022 | 6 | +0.425 |
| 2023 | 5 | -0.458 |
| 2024 | 7 | -0.613 |
| 2025 | 4 | -0.289 |
| 2026 | 6 | -0.694 |

| exit | trades | avg R |
|---|---|---|
| flat | 1 | +0.911 |
| stop | 22 | -1.021 |
| target | 9 | +1.857 |

Variant no_trend_filter: 154 trades, avg -0.091R
Engine e59d49c4203e (fill-minute targets, open-first ordering, market slippage 10% of spread).
Look-ahead audit: 10 signals re-run on truncated data (time, side, stop, target, entry price and risk limits compared), 0 changed.
