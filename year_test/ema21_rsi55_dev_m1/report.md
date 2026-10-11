# Rule test: ema21_rsi55 on dev_m1

Rule (frozen before testing): 15m candle closes above EMA21 (previous close at/below it) with RSI(14) > 55 → buy at the ask on the next minute; exit at the bid on the next minute after the first 15m close below EMA21. Long only, no stop. R = ATR(14) of 15m candles at entry. Real OANDA bid/ask; 2× costs pays the spread again on both sides. Versions: 24h = as written (forced out before closures > 60 min); day = entries 02:00–15:30 NY, flat 15:50 NY.

Trades span 2024-10-01 → 2026-09-30. Pass = ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs.

| Symbol | Version | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread paid (R) | Thirds | Median hold | Overnight | Pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AUDUSD | 24h | 639 | 22% | -0.477 | -0.684 to -0.304 | -304.6 | -1.150 | 0.674 | -0.37 / -0.67 / -0.39 | 90 min | 10% | no |
| AUDUSD | day | 396 | 25% | -0.344 | -0.565 to -0.108 | -136.2 | -0.843 | 0.499 | -0.28 / -0.51 / -0.24 | 90 min | 0% | no |
| EURUSD | 24h | 587 | 24% | -0.320 | -0.553 to -0.117 | -187.9 | -0.913 | 0.593 | -0.30 / -0.28 / -0.38 | 90 min | 10% | no |
| EURUSD | day | 396 | 26% | -0.298 | -0.519 to -0.068 | -118.1 | -0.790 | 0.492 | -0.47 / -0.08 / -0.34 | 90 min | 0% | no |
| GBPUSD | 24h | 646 | 24% | -0.433 | -0.664 to -0.275 | -279.7 | -1.051 | 0.619 | -0.19 / -0.57 / -0.53 | 90 min | 9% | no |
| GBPUSD | day | 447 | 25% | -0.414 | -0.616 to -0.201 | -185.2 | -0.887 | 0.473 | -0.31 / -0.48 / -0.46 | 80 min | 0% | no |
| NDQ | 24h | 587 | 32% | +0.065 | -0.188 to +0.332 | +38.1 | -0.074 | 0.139 | -0.04 / +0.10 / +0.14 | 90 min | 8% | no |
| NDQ | day | 434 | 31% | +0.108 | -0.209 to +0.467 | +46.9 | -0.024 | 0.132 | -0.01 / +0.04 / +0.29 | 90 min | 0% | no |
| US30 | 24h | 616 | 31% | +0.250 | -0.085 to +0.602 | +154.1 | +0.069 | 0.181 | +0.29 / +0.48 / -0.03 | 90 min | 5% | no |
| US30 | day | 492 | 33% | +0.286 | -0.095 to +0.721 | +140.6 | +0.103 | 0.183 | +0.30 / +0.77 / -0.21 | 90 min | 0% | no |
| XAUUSD | 24h | 594 | 34% | +0.147 | -0.085 to +0.311 | +87.3 | -0.111 | 0.258 | +0.05 / +0.33 / +0.06 | 90 min | 11% | no |
| XAUUSD | day | 371 | 33% | +0.079 | -0.177 to +0.373 | +29.3 | -0.147 | 0.226 | -0.30 / +0.36 / +0.18 | 90 min | 0% | no |
