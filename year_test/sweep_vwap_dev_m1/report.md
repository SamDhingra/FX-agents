# Gold scalp #2: liquidity sweep + VWAP (15m → 5m → 3m) (dev_m1) — **no pass**

2024-10-01 → 2026-09-30, XAUUSD, entries 08:00–11:30 NY. Rules as given (Oct 19 2026); open points fixed in fxagents/sweep_vwap.py before this run. Real OANDA bid/ask fills; R is for the whole position (70% at 1.5R, 30% runner to 3R), after spread; 2× costs pays one more spread. OANDA Canada's 1% conversion fee on CAD-account P&L is not included (≈ −0.01R/trade).

Pass = ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, better than the coin flip and than the same trigger without the 15m bias.

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 525 | 38% | -0.073 | -0.17 to +0.03 | -0.180 | -0.060 | -0.085 | -38.5 | -2,295 | 25 min |
| coin-flip control | 525 | 38% | -0.086 | -0.19 to +0.02 | -0.192 | -0.143 | -0.037 | -44.9 | -4,017 | 25 min |
| no 15m bias | 639 | 37% | -0.096 | -0.19 to -0.01 | -0.204 | -0.122 | -0.074 | -61.6 | -2,786 | 24 min |

| Bias | Side | Trades | Win | Avg R |
|---|---|---|---|---|
| ema | short | 185 | 39% | -0.032 |
| ema | long | 236 | 34% | -0.178 |
| sweep | short | 60 | 43% | +0.089 |
| sweep | long | 44 | 50% | +0.095 |

Exits: stop 60%, runner_stop 19%, runner_target 15%, flat_1630 6%, closure 0%. Reached TP1 (+1.5R): 37%. Typical stop distance $6.60 (middle half $4.33–$10.75); typical spread $0.62 = 9% of the stop.

