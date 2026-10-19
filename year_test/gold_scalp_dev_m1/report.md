# Gold scalp: 15m trend → 5m breakout + retest → 3m confirmation (dev_m1) — **no pass**

2024-10-02 → 2026-09-30, XAUUSD. Rules as given (Oct 19 2026); open points fixed in fxagents/gold_scalp.py before this run. Real OANDA bid/ask fills; R includes the spread ("2× costs" pays one more spread). Stop beyond the retest extreme + 0.25 ATR(5m), target 2× the chart stop, 30-minute time exit, spread ≤ 20% of the stop, no trades after two straight losses in a day, no entries 16:00–18:30 NY or near USD releases.

Pass = ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, better than the coin flip and than the same rule without the 15m trend filter.

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 1073 | 42% | -0.075 | -0.13 to -0.03 | -0.173 | -0.072 | -0.078 | -80.8 | -3,529 | 30 min |
| coin-flip control | 1073 | 42% | -0.098 | -0.15 to -0.04 | -0.196 | -0.186 | -0.022 | -105.7 | -5,919 | 31 min |
| no 15m trend filter | 1556 | 40% | -0.112 | -0.17 to -0.08 | -0.214 | -0.123 | -0.104 | -175.0 | -10,524 | 30 min |

## Where it trades

| Session (NY time) | Trades | Win | Avg R |
|---|---|---|---|
| Asia 18–02 | 366 | 43% | -0.107 |
| London 02–08 | 319 | 41% | -0.068 |
| NY afternoon 12–16 | 132 | 39% | -0.120 |
| NY morning 08–12 | 256 | 44% | -0.016 |

| Side | Trades | Avg R |
|---|---|---|
| short | 440 | -0.100 |
| long | 633 | -0.058 |

Exits: time_stop 59%, stop 33%, target 8%. Typical chart stop: 6.35 (median), 4.17–10.14 (middle half); typical entry spread 0.61, = 9% of the stop.

