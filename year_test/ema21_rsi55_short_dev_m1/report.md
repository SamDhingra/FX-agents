# Rule test: ema21_rsi55_short on dev_m1

Base rule (frozen before testing): candle closes above EMA21 (previous close at/below it) with RSI(14) > 55 → buy at the ask on the next minute; exit at the bid on the next minute after the first close below EMA21. Short (mirror): close below EMA21 (previous at/above) with RSI(14) < 45 → sell at the bid; exit at the ask after the first close above EMA21. Side both = long and short trades together. No stop. R = ATR(14) of that timeframe at entry. Real OANDA bid/ask (one spread per round trip, already in every result); 2× costs pays that spread once more. Versions: 24h = as written (forced out before closures > 60 min); day = entries 02:00–15:30 NY, flat 15:50 NY. Volume rvol≥1 = the signal candle's tick volume at least the median of the same time-of-day candle over the previous 20 days. Add = one extra equal unit, once, on a later close above EMA21 with 58 < RSI ≤ 70 while above the entry price; R is per initial unit, so an added trade's R counts both units.

Trades span 2024-10-01 → 2026-09-30. Pass = ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs. **0 of 12 variants pass.** With 12 variants, about 0 could pass by luck alone, so anything that passes here goes to the holdout once, unchanged, before it counts.

| Symbol | Side | TF | Version | Volume | Add | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread (R) | Thirds | Median hold | Pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NDQ | short | 15min | 24h | — | — | 567 | 25% | -0.115 | -0.344 to +0.182 | -64.9 | -0.180 | 0.065 | -0.04 / -0.10 / -0.20 | 90 min | no |
| NDQ | short | 15min | day | — | — | 429 | 26% | -0.093 | -0.392 to +0.225 | -39.9 | -0.154 | 0.061 | +0.09 / -0.06 / -0.31 | 80 min | no |
| NDQ | both | 15min | 24h | — | — | 1154 | 29% | -0.023 | -0.194 to +0.174 | -26.9 | -0.091 | 0.067 | -0.03 / +0.03 / -0.07 | 90 min | no |
| NDQ | both | 15min | day | — | — | 863 | 29% | +0.008 | -0.207 to +0.248 | +7.0 | -0.055 | 0.064 | +0.04 / -0.01 / +0.00 | 90 min | no |
| US30 | short | 15min | 24h | — | — | 609 | 28% | -0.115 | -0.311 to +0.115 | -70.3 | -0.198 | 0.082 | -0.07 / -0.18 / -0.10 | 75 min | no |
| US30 | short | 15min | day | — | — | 497 | 30% | -0.103 | -0.335 to +0.146 | -51.1 | -0.187 | 0.084 | +0.00 / -0.28 / -0.03 | 80 min | no |
| US30 | both | 15min | 24h | — | — | 1225 | 30% | +0.068 | -0.112 to +0.270 | +83.8 | -0.018 | 0.086 | +0.09 / +0.24 / -0.13 | 90 min | no |
| US30 | both | 15min | day | — | — | 989 | 31% | +0.090 | -0.123 to +0.326 | +89.5 | +0.003 | 0.088 | +0.14 / +0.37 / -0.24 | 90 min | no |
| XAUUSD | short | 15min | 24h | — | — | 531 | 26% | -0.023 | -0.251 to +0.289 | -12.4 | -0.142 | 0.118 | -0.15 / -0.07 / +0.15 | 90 min | no |
| XAUUSD | short | 15min | day | — | — | 334 | 26% | +0.071 | -0.245 to +0.444 | +23.8 | -0.037 | 0.108 | +0.03 / -0.04 / +0.22 | 90 min | no |
| XAUUSD | both | 15min | 24h | — | — | 1125 | 30% | +0.067 | -0.104 to +0.243 | +74.9 | -0.057 | 0.124 | -0.04 / +0.14 / +0.10 | 90 min | no |
| XAUUSD | both | 15min | day | — | — | 705 | 30% | +0.075 | -0.140 to +0.327 | +53.1 | -0.036 | 0.111 | -0.14 / +0.18 / +0.19 | 90 min | no |

## Pips (after the real spread)

1 pip = 0.0001 for FX majors, 0.10 for gold, 1 point for NDQ/US30. With adds, pips count both units.

| Symbol | Side | TF | Version | Volume | Add | Trades | Pips won | Pips lost | Net pips | Avg win | Avg loss | Spread per trade | Largest win / loss |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NDQ | short | 15min | 24h | — | — | 567 | +17,307 | -21,622 | **-4,315** | +121.9 | -50.9 | 2.0 | +1011 / -855 |
| NDQ | short | 15min | day | — | — | 429 | +14,625 | -17,102 | **-2,477** | +129.4 | -54.1 | 1.8 | +660 / -855 |
| NDQ | both | 15min | 24h | — | — | 1154 | +36,553 | -39,645 | **-3,092** | +110.4 | -48.2 | 2.0 | +2008 / -855 |
| NDQ | both | 15min | day | — | — | 863 | +30,739 | -31,821 | **-1,082** | +123.9 | -51.7 | 1.8 | +1912 / -855 |
| US30 | short | 15min | 24h | — | — | 609 | +26,683 | -28,673 | **-1,990** | +154.2 | -65.8 | 3.4 | +996 / -447 |
| US30 | short | 15min | day | — | — | 497 | +23,592 | -24,558 | **-966** | +160.5 | -70.2 | 3.5 | +766 / -447 |
| US30 | both | 15min | 24h | — | — | 1225 | +59,736 | -55,196 | **+4,540** | +165.0 | -64.0 | 3.4 | +3263 / -563 |
| US30 | both | 15min | day | — | — | 989 | +52,719 | -47,870 | **+4,848** | +171.7 | -70.2 | 3.5 | +2999 / -563 |
| XAUUSD | short | 15min | 24h | — | — | 531 | +33,513 | -29,970 | **+3,543** | +239.4 | -76.7 | 7.1 | +2019 / -500 |
| XAUUSD | short | 15min | day | — | — | 334 | +22,999 | -18,819 | **+4,181** | +261.4 | -76.5 | 6.6 | +2254 / -500 |
| XAUUSD | both | 15min | 24h | — | — | 1125 | +68,735 | -58,528 | **+10,207** | +201.0 | -74.7 | 7.2 | +2019 / -526 |
| XAUUSD | both | 15min | day | — | — | 705 | +44,790 | -37,819 | **+6,971** | +211.3 | -76.7 | 6.7 | +2254 / -526 |

## Volume: how the base rule did by the signal candle's relative volume

Descriptive only (no add, no volume filter). Buckets were fixed before the run; reading the best bucket and filtering on it would be fitting to this data.

| Symbol | Side | TF | Version | rvol < 0.8: trades / win / avg R | rvol 0.8–1.2: trades / win / avg R | rvol 1.2–2.0: trades / win / avg R | rvol ≥ 2.0: trades / win / avg R |
|---|---|---|---|---|---|---|---|
| NDQ | short | 15min | 24h | 59 / 19% / +0.23 | 225 / 27% / -0.03 | 188 / 27% / +0.05 | 82 / 21% / -0.86 |
| NDQ | short | 15min | day | 48 / 17% / -0.05 | 190 / 27% / -0.01 | 130 / 32% / +0.18 | 51 / 22% / -0.96 |
| NDQ | both | 15min | 24h | 169 / 23% / +0.31 | 481 / 30% / -0.04 | 341 / 30% / +0.00 | 137 / 29% / -0.44 |
| NDQ | both | 15min | day | 126 / 21% / +0.38 | 394 / 30% / -0.01 | 238 / 31% / +0.06 | 84 / 27% / -0.57 |
| US30 | short | 15min | 24h | 121 / 20% / -0.55 | 195 / 31% / -0.00 | 152 / 30% / -0.18 | 126 / 30% / +0.27 |
| US30 | short | 15min | day | 101 / 20% / -0.56 | 164 / 32% / +0.00 | 127 / 31% / -0.31 | 91 / 34% / +0.59 |
| US30 | both | 15min | 24h | 290 / 25% / +0.23 | 367 / 31% / -0.04 | 303 / 31% / -0.04 | 239 / 30% / +0.11 |
| US30 | both | 15min | day | 235 / 27% / +0.21 | 311 / 33% / -0.03 | 242 / 33% / -0.06 | 176 / 31% / +0.24 |
| XAUUSD | short | 15min | 24h | 109 / 25% / -0.07 | 183 / 22% / -0.26 | 160 / 32% / +0.29 | 61 / 26% / +0.05 |
| XAUUSD | short | 15min | day | 64 / 22% / +0.03 | 128 / 25% / -0.19 | 100 / 30% / +0.42 | 29 / 28% / +0.21 |
| XAUUSD | both | 15min | 24h | 246 / 29% / -0.13 | 404 / 30% / +0.06 | 318 / 30% / +0.19 | 130 / 35% / +0.26 |
| XAUUSD | both | 15min | day | 144 / 29% / -0.04 | 273 / 30% / +0.01 | 201 / 29% / +0.22 | 70 / 37% / +0.24 |

Jev (the bot's LLM grader) is not in this backtest: asking a model today to grade 2024–2026 candles is not a clean test (it may know what happened next). It can only be tested forward, by logging its grade on live signals.
