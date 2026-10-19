# Pre-registered: gold sweep + VWAP, sweep-only (dev_m1,holdout_m1)

Exactly the sweep + VWAP rule (fxagents/sweep_vwap.py) minus the 50-EMA fallback: only a 15m sweep of the Asian / London / previous-day high or low sets the direction. Frozen Oct 19 2026 after the dev report, before any holdout data was read. Dev = where the idea came from (shown only); **the holdout alone decides**. Pass = ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, better than the coin flip. Real OANDA bid/ask fills; R for the whole position after spread.

| Data | Role | Verdict | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Coin flip | Total R |
|---|---|---|---|---|---|---|---|---|---|---|---|
| dev_m1 | shown | (in-sample) | 106 | 46% | +0.091 | -0.12 to +0.33 | -0.006 | -0.043 | +0.219 | -0.011 | +9.6 |
| holdout_m1 | judged | **no pass** | 157 | 32% | -0.225 | -0.40 to -0.04 | -0.323 | -0.236 | -0.212 | -0.164 | -35.4 |

| Data | Long avg R (n) | Short avg R (n) | Reached TP1 | Typical stop | Typical spread |
|---|---|---|---|---|---|
| dev_m1 | +0.117 (45) | +0.071 (61) | 43% | $7.06 | $0.61 |
| holdout_m1 | -0.210 (82) | -0.242 (75) | 30% | $3.58 | $0.30 |
