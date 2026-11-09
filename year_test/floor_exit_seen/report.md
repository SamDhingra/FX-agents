# Floor exit for ICT OTE / DTFX Zone: seen

Registered Nov 9 2026 (research/floor_exit/PREREGISTRATION_2026-11-09.md). Before the first target, exit at the next minute's open when a completed 5m/15m candle closes beyond the setup's own floor (79% / 85% of the leg) while the trade is losing. Baseline: today's standard profile, same entries. Real bid/ask per minute.

Cohort 15,768 entries (default parameters, live bias rule, entry windows, news). Engine check: the replay reproduces 100.0% (required 98%); reconstructable with a floor: 100.0% (required 90%).

| entries | eligible | changed (halves) | avg R baseline | avg R floor exit | mean d (95% range) | halves | 2× spread | placebo mean d | placebo p | at ≤ −1R: baseline → rule | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 15,768 | 15,768 | 4,357 (2304 / 2053) | -0.070 | -0.072 | -0.003 (-0.009 to +0.004) | -0.006 / +0.001 | -0.004 | -0.001 | 0.891 | 44.1% → 22.8% | fail: 95% range above 0, both halves > 0, 2× spread > 0, beats the placebo (p < 0.05) |

## Information

- trades cut that would have hit the stop: 3,364, R saved +943.9; cut that would have recovered: 993, R lost -984.4
- worst 5% of trades: -1.02R → -1.02R · max drawdown 1111.5R → 1150.6R

| setup · instrument · tf | entries | baseline R | floor-exit R | changed |
|---|---|---|---|---|
| dtfx_zone NDQ 15min | 805 | -0.073 | -0.074 | 125 |
| dtfx_zone NDQ 5min | 2094 | -0.061 | -0.055 | 578 |
| dtfx_zone US30 15min | 819 | -0.091 | -0.094 | 140 |
| dtfx_zone US30 5min | 2175 | -0.090 | -0.090 | 606 |
| dtfx_zone XAUUSD 15min | 917 | -0.052 | -0.057 | 151 |
| dtfx_zone XAUUSD 5min | 2045 | -0.092 | -0.089 | 488 |
| ict_ote NDQ 15min | 869 | -0.000 | -0.006 | 211 |
| ict_ote NDQ 5min | 1533 | -0.053 | -0.053 | 515 |
| ict_ote US30 15min | 844 | -0.063 | -0.080 | 260 |
| ict_ote US30 5min | 1569 | -0.034 | -0.047 | 570 |
| ict_ote XAUUSD 15min | 737 | -0.071 | -0.058 | 211 |
| ict_ote XAUUSD 5min | 1361 | -0.122 | -0.138 | 502 |

**Did not pass: per the registration the floor exit is closed; nothing else is tried on these results.**

A pass does not make a still-negative setup tradable.
