# Chart patterns as entry signals — stage 2 (dev_m1)

2024-10-01 → 2026-09-30. XAUUSD, NDQ, US30 on 15m and 1h bars. Pattern definitions are the chart overlay's, unchanged; the signal is causal (the last pivot must be confirmed, entry on the next minute after the trigger bar's close), stops and targets fixed at entry, exit at the stop, the target, 30 bars or 15:50 NY. Real OANDA bid/ask fills; R includes the spread. Rules frozen in fxagents/pattern_test.py before this run.

Pass (per family, everything pooled) = ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves of the period, and better than the coin-flip control. Six families are tested at once, so a pass is only a candidate for the untouched holdout.

| Family | Verdict | Trades | Win | Avg R | 95% range | Avg R 2× costs | 1st half | 2nd half | Coin-flip avg R | Total R |
|---|---|---|---|---|---|---|---|---|---|---|
| Double top / bottom | **no pass** | 1786 | 48% | -0.028 | -0.07 to +0.01 | -0.057 | -0.061 | +0.002 | -0.030 | -50.3 |
| Head & shoulders (and inverse) | **no pass** | 700 | 44% | -0.078 | -0.15 to -0.01 | -0.111 | -0.090 | -0.067 | -0.093 | -54.6 |
| Triangles | **no pass** | 2838 | 36% | -0.072 | -0.12 to -0.02 | -0.126 | -0.073 | -0.071 | -0.063 | -204.5 |
| Wedges | **no pass** | 2769 | 40% | -0.054 | -0.10 to -0.01 | -0.089 | -0.031 | -0.076 | -0.045 | -149.8 |
| Channels | **no pass** | 427 | 41% | -0.072 | -0.17 to +0.03 | -0.096 | -0.007 | -0.130 | +0.019 | -30.8 |
| Flags | **no pass** | 1272 | 44% | -0.010 | -0.09 to +0.05 | -0.040 | -0.045 | +0.027 | -0.002 | -12.3 |

## By instrument × timeframe (avg R, trades)

| Family | XAUUSD 15m | XAUUSD 60m | NDQ 15m | NDQ 60m | US30 15m | US30 60m |
|---|---|---|---|---|---|---|
| Double top / bottom | -0.020 (549) | +0.040 (135) | -0.016 (450) | -0.046 (99) | -0.054 (455) | -0.089 (98) |
| Head & shoulders (and inverse) | -0.031 (220) | -0.081 (42) | -0.127 (187) | -0.009 (47) | -0.115 (157) | -0.050 (47) |
| Triangles | -0.116 (785) | +0.069 (224) | -0.094 (724) | -0.023 (200) | -0.076 (695) | -0.018 (210) |
| Wedges | -0.099 (743) | +0.040 (219) | -0.060 (735) | -0.057 (193) | -0.019 (683) | -0.083 (196) |
| Channels | -0.032 (114) | +0.046 (38) | -0.206 (115) | -0.213 (26) | +0.034 (102) | -0.100 (32) |
| Flags | +0.037 (275) | +0.086 (90) | -0.022 (320) | -0.041 (142) | -0.038 (298) | -0.041 (147) |

## By pattern and direction (avg R, trades)

| Pattern | Long | Short | Exit reasons |
|---|---|---|---|
| ascending triangle | -0.023 (194) | — | stop 48%, flat_1550 23%, target 20%, time_stop 9%, closure 1% |
| bear flag | — | -0.096 (467) | stop 44%, flat_1550 28%, target 14%, time_stop 13%, closure 1% |
| bull flag | +0.040 (805) | — | stop 37%, flat_1550 36%, time_stop 13%, target 12%, closure 1% |
| channel down | — | -0.131 (199) | stop 41%, flat_1550 29%, time_stop 20%, target 11% |
| channel up | -0.021 (228) | — | flat_1550 44%, stop 35%, time_stop 11%, target 9%, closure 2% |
| descending triangle | — | -0.137 (170) | stop 56%, target 19%, flat_1550 18%, time_stop 8% |
| double bottom | -0.004 (868) | — | stop 34%, target 31%, flat_1550 25%, time_stop 10%, closure 1% |
| double top | — | -0.052 (918) | stop 36%, target 33%, flat_1550 21%, time_stop 9%, closure 1% |
| falling wedge | -0.051 (1204) | — | stop 44%, flat_1550 26%, time_stop 14%, target 13%, closure 2%, end 0% |
| head shoulders | — | -0.113 (325) | stop 42%, target 28%, flat_1550 23%, time_stop 6% |
| inverse head shoulders | -0.048 (375) | — | stop 38%, flat_1550 27%, target 23%, time_stop 10%, closure 1% |
| rising wedge | — | -0.057 (1565) | stop 41%, flat_1550 26%, time_stop 16%, target 15%, closure 1% |
| symmetrical triangle | -0.128 (1208) | -0.017 (1266) | stop 55%, target 21%, flat_1550 17%, time_stop 6%, closure 1% |

Pips (all families): XAUUSD: 3434 trades, net +20,326 pips after spread; NDQ: 3238 trades, net -20,904 pips after spread; US30: 3120 trades, net -11,823 pips after spread.

