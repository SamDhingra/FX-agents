# Gemini's gold strategies on dev_m1

Data 2024-09-30 → 2026-09-30. Rules exactly as specified by Gemini (2026-10-17), with the open points fixed in fxagents/gemini_test.py before any run. Real OANDA bid/ask fills; R includes the spread; 2× costs pays one more. Pass = ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs — and the rule must beat its controls. #1 uses the verified calendar (FOMC, CPI, NFP, PPI only).

## #2 London-to-NY momentum — **no pass**

| Rule | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread (R) | Long avg R (n) | Short avg R (n) | Thirds | Median hold | Net pips | Exits |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rule | 9 | 67% | -0.012 | -0.47 to +0.38 | -0.1 | -0.046 | 0.034 | -0.073 (5) | +0.066 (4) | +0.26 / -0.40 / +0.11 | 63 min | -218 | stop 7, flat_1550 1, check 1 |
| coin-flip control | 9 | 44% | +0.115 | -0.60 to +1.09 | +1.0 | +0.081 | 0.034 | -0.210 (5) | +0.520 (4) | -0.68 / +0.90 / +0.12 | 107 min | +475 | stop 5, check 2, flat_1550 1, target 1 |
| dead-London control | 0 | | | | | | | | | | | | |

## #3 Cross-asset US cash open — **no pass**

| Rule | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread (R) | Long avg R (n) | Short avg R (n) | Thirds | Median hold | Net pips | Exits |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rule | 9 | 56% | +0.214 | -0.52 to +1.00 | +1.9 | +0.175 | 0.039 | +1.129 (4) | -0.518 (5) | -0.20 / +1.19 / -0.35 | 150 min | +182 | stop 5, time_stop 3, target 1 |
| coin-flip control | 9 | 44% | -0.397 | -0.80 to +0.02 | -3.6 | -0.436 | 0.039 | -0.040 (5) | -0.842 (4) | -0.15 / -0.39 / -0.66 | 132 min | -713 | stop 5, time_stop 3, flat_1550 1 |
| shuffled-equity control | 11 | 64% | +0.185 | -0.25 to +0.67 | +2.0 | +0.144 | 0.042 | +0.185 (6) | +0.186 (5) | -0.03 / +0.46 / +0.11 | 150 min | +397 | stop 6, time_stop 4, flat_1550 1 |

## #1 Post-release drift — **no pass**

| Rule | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread (R) | Long avg R (n) | Short avg R (n) | Thirds | Median hold | Net pips | Exits |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rule | 2 | 50% | -0.251 | -1.00 to +0.50 | -0.5 | -0.314 | 0.063 | -0.251 (2) | — (0) | +0.50 / -1.00 | 42 min | -56 | stop 2 |
| coin-flip control | 2 | 0% | -0.547 | -1.00 to -0.09 | -1.1 | -0.610 | 0.063 | — (0) | -0.547 (2) | -1.00 / -0.09 | 88 min | -101 | stop 2 |
| no-news-day control | 12 | 67% | +0.418 | -0.30 to +1.09 | +5.0 | +0.369 | 0.049 | +0.660 (9) | -0.309 (3) | -0.11 / +0.73 / +0.63 | 126 min | +468 | stop 7, time_stop 3, target 2 |

## Why so few trades: how many days pass each condition

Each evaluated day (or release bar for #1) counted once. *Alone* = share passing that condition by itself; *cumulative* = days still left after it and every condition above it (in the rule's order).

**#2 London-to-NY momentum** — 480 days evaluated

| Condition | Alone | Cumulative (days) |
|---|---|---|
| disp_ge_0_8 | 18% | 86 |
| range_le_2_2 | 96% | 68 |
| eff_ge_0_55 | 35% | 64 |
| vol_ge_1_15 | 35% | 27 |
| ema4h_agrees | 62% | 19 |
| open_holds | 31% | 18 |
| filled | 2% | 9 |

**#3 Cross-asset US cash open** — 479 days evaluated

| Condition | Alone | Cumulative (days) |
|---|---|---|
| nas_vol_ge_1_15 | 23% | 108 |
| range_0_8_to_2_5_atr | 73% | 78 |
| close_in_range_third | 68% | 51 |
| ema1h_agrees | 57% | 29 |
| equity_confirms | 44% | 12 |
| filled | 2% | 9 |

**#1 Post-release drift** — 81 days evaluated

| Condition | Alone | Cumulative (days) |
|---|---|---|
| range_1_35_to_3_5_atr | 51% | 41 |
| range_ge_1_35_atr (lower bound only, info) | 93% | — |
| vol_ge_1_4 | 85% | 32 |
| body_ge_0_55 | 37% | 11 |
| close_near_extreme | 47% | 7 |
| ema1h_agrees | 70% | 6 |
| filled | 2% | 2 |

