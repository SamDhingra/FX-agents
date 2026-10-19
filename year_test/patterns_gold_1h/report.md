# Pre-registered: chart patterns on gold 1h, all families as one rule (dev_m1,holdout_m1)

Frozen Oct 19 2026 after the dev report, before any holdout data was read (fxagents/pattern_test.py, PREREG). Dev numbers are where the idea came from (in-sample, shown only); **the holdout alone decides**. Pass = ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, better than the coin-flip control. Real OANDA bid/ask fills; R includes the spread.

| Data | Role | Verdict | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Coin flip | Total R |
|---|---|---|---|---|---|---|---|---|---|---|---|
| dev_m1 | shown | (in-sample) | 748 | 48% | +0.048 | -0.04 to +0.09 | +0.021 | +0.040 | +0.054 | +0.003 | +35.6 |
| holdout_m1 | judged | **no pass** | 1420 | 41% | -0.053 | -0.09 to +0.02 | -0.089 | -0.072 | -0.033 | -0.003 | -75.9 |

## By family (avg R, trades)

| Family | dev_m1 | holdout_m1 |
|---|---|---|
| Double top / bottom | +0.040 (135) | -0.011 (245) |
| Head & shoulders (and inverse) | -0.081 (42) | +0.016 (102) |
| Triangles | +0.069 (224) | -0.082 (438) |
| Wedges | +0.040 (219) | -0.028 (365) |
| Channels | +0.046 (38) | -0.075 (57) |
| Flags | +0.086 (90) | -0.113 (213) |

## Long vs short (avg R, trades)

| Data | Long | Short |
|---|---|---|
| dev_m1 | +0.051 (386) | +0.044 (362) |
| holdout_m1 | -0.025 (725) | -0.083 (695) |
