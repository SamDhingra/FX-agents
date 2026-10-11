# Rule test: ema21_rsi55 on dev_m1

Rule (frozen before testing): 15m candle closes above EMA21 (previous close at/below it) with RSI(14) > 55 → buy at the ask on the next minute; exit at the bid on the next minute after the first 15m close below EMA21. Long only, no stop. R = ATR(14) of 15m candles at entry. Real OANDA bid/ask (one spread per round trip, already in every result); 2× costs pays that spread once more. Versions: 24h = as written (forced out before closures > 60 min); day = entries 02:00–15:30 NY, flat 15:50 NY.

Trades span 2024-10-01 → 2026-09-30. Pass = ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs.

| Symbol | Version | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread paid (R) | Thirds | Median hold | Overnight | Pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AUDUSD | 24h | 639 | 22% | -0.477 | -0.684 to -0.304 | -304.6 | -0.814 | 0.337 | -0.37 / -0.67 / -0.39 | 90 min | 10% | no |
| AUDUSD | day | 396 | 25% | -0.344 | -0.565 to -0.108 | -136.2 | -0.593 | 0.249 | -0.28 / -0.51 / -0.24 | 90 min | 0% | no |
| EURUSD | 24h | 587 | 24% | -0.320 | -0.553 to -0.117 | -187.9 | -0.617 | 0.296 | -0.30 / -0.28 / -0.38 | 90 min | 10% | no |
| EURUSD | day | 396 | 26% | -0.298 | -0.519 to -0.068 | -118.1 | -0.544 | 0.246 | -0.47 / -0.08 / -0.34 | 90 min | 0% | no |
| GBPUSD | 24h | 646 | 24% | -0.433 | -0.664 to -0.275 | -279.7 | -0.742 | 0.309 | -0.19 / -0.57 / -0.53 | 90 min | 9% | no |
| GBPUSD | day | 447 | 25% | -0.414 | -0.616 to -0.201 | -185.2 | -0.651 | 0.236 | -0.31 / -0.48 / -0.46 | 80 min | 0% | no |
| NDQ | 24h | 587 | 32% | +0.065 | -0.188 to +0.332 | +38.1 | -0.005 | 0.069 | -0.04 / +0.10 / +0.14 | 90 min | 8% | no |
| NDQ | day | 434 | 31% | +0.108 | -0.209 to +0.467 | +46.9 | +0.042 | 0.066 | -0.01 / +0.04 / +0.29 | 90 min | 0% | no |
| US30 | 24h | 616 | 31% | +0.250 | -0.085 to +0.602 | +154.1 | +0.160 | 0.090 | +0.29 / +0.48 / -0.03 | 90 min | 5% | no |
| US30 | day | 492 | 33% | +0.286 | -0.095 to +0.721 | +140.6 | +0.195 | 0.091 | +0.30 / +0.77 / -0.21 | 90 min | 0% | no |
| XAUUSD | 24h | 594 | 34% | +0.147 | -0.085 to +0.311 | +87.3 | +0.018 | 0.129 | +0.05 / +0.33 / +0.06 | 90 min | 11% | no |
| XAUUSD | day | 371 | 33% | +0.079 | -0.177 to +0.373 | +29.3 | -0.034 | 0.113 | -0.30 / +0.36 / +0.18 | 90 min | 0% | no |

## Pips (after the real spread)

1 pip = 0.0001 for FX majors, 0.10 for gold, 1 point for NDQ/US30. Pips won = sum over winning trades; pips lost = sum over losing trades; the spread is already inside both (it is shown separately so you can see its weight).

| Symbol | Version | Trades | Pips won | Pips lost | Net pips | Avg win | Avg loss | Avg per trade | Spread per trade | Spread total | Largest win / loss |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AUDUSD | 24h | 639 | +2,133 | -3,508 | **-1,374** | +15.1 | -7.0 | -2.2 | 1.6 | 1,007 | +116 / -49 |
| AUDUSD | day | 396 | +1,446 | -2,133 | **-687** | +14.5 | -7.2 | -1.7 | 1.3 | 524 | +70 / -28 |
| EURUSD | 24h | 587 | +2,861 | -3,794 | **-933** | +20.2 | -8.5 | -1.6 | 1.7 | 982 | +178 / -38 |
| EURUSD | day | 396 | +2,068 | -2,778 | **-710** | +20.3 | -9.4 | -1.8 | 1.6 | 625 | +96 / -38 |
| GBPUSD | 24h | 646 | +3,227 | -5,042 | **-1,815** | +20.8 | -10.3 | -2.8 | 2.2 | 1,418 | +163 / -72 |
| GBPUSD | day | 447 | +2,298 | -3,693 | **-1,396** | +20.5 | -11.0 | -3.1 | 1.9 | 842 | +110 / -71 |
| NDQ | 24h | 587 | +19,246 | -18,022 | **+1,224** | +101.8 | -45.3 | +2.1 | 2.0 | 1,173 | +2008 / -427 |
| NDQ | day | 434 | +16,114 | -14,720 | **+1,394** | +119.4 | -49.2 | +3.2 | 1.8 | 801 | +1912 / -427 |
| US30 | 24h | 616 | +33,053 | -26,523 | **+6,530** | +174.9 | -62.1 | +10.6 | 3.5 | 2,130 | +3263 / -563 |
| US30 | day | 492 | +29,127 | -23,313 | **+5,814** | +182.0 | -70.2 | +11.8 | 3.5 | 1,722 | +2999 / -563 |
| XAUUSD | 24h | 594 | +35,222 | -28,558 | **+6,664** | +174.4 | -72.9 | +11.2 | 7.2 | 4,262 | +1092 / -526 |
| XAUUSD | day | 371 | +21,791 | -19,000 | **+2,790** | +175.7 | -76.9 | +7.5 | 6.8 | 2,512 | +1079 / -526 |
