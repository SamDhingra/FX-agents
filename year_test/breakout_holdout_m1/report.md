# Gold Breakout 15M (WillyAlgoTrader) on holdout_m1 — frozen dev passers only

Author's defaults (fxagents/breakout_test.py docstring): range = high/low 00:00–07:00 GMT+3; from 07:00 a buy stop at the range high and a sell stop at the range low (one cancels the other, one trade a day); stop 1% of entry (or the opposite side of the range); no target; flat at the close hour (default 20:00 GMT+3 = 17:00 UTC). Earlier closes (12/14/16:00 GMT+3) added to shorten the hold. Real OANDA bid/ask fills; R includes the spread.

**Primary (gold, 1% stop, 20:00 close): 960 trades, avg +0.022R (95% -0.02 to +0.07), 2× costs +0.006R → no pass.**

Pass = ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs. **0 of 3 cells pass.** The coin-flip control enters at the same minute in a random direction with the same stop and close: the breakout only adds something if it beats its control.

| Symbol | Stop | Close (GMT+3) | Rule | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread (R) | Stopped | Median hold (h) | Long avg R (n) | Short avg R (n) | Thirds | Net pips | Pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 1% of entry | 20:00 | **breakout** | 960 | 48% | +0.022 | -0.02 to +0.07 | +21.5 | +0.006 | 0.017 | 12% | 11.3 | +0.024 (492) | +0.020 (468) | +0.05 / -0.01 / +0.03 | +4,539 | no |
| XAUUSD | 1% of entry | 20:00 | coin-flip control | 960 | 49% | -0.006 | -0.05 to +0.04 | -5.8 | -0.023 | 0.017 | 15% | 11.2 | +0.005 (487) | -0.018 (473) | +0.02 / +0.01 / -0.04 | -2,097 | no |
| XAUUSD | 1% of entry | 16:00 | breakout | 940 | 49% | -0.000 | -0.02 to +0.03 | -0.4 | -0.017 | 0.016 | 3% | 7.5 | +0.000 (482) | -0.001 (458) | +0.02 / -0.00 / -0.02 | -173 | no |
| XAUUSD | 1% of entry | 16:00 | coin-flip control | 940 | 49% | -0.022 | -0.05 to +0.01 | -20.5 | -0.038 | 0.016 | 5% | 7.5 | -0.020 (479) | -0.024 (461) | -0.03 / -0.04 / -0.00 | -3,849 | no |
| XAUUSD | range boundary | 20:00 | breakout | 960 | 36% | +0.004 | -0.08 to +0.10 | +4.0 | -0.038 | 0.042 | 51% | 8.7 | +0.012 (492) | -0.004 (468) | +0.01 / -0.01 / +0.01 | +130 | no |
| XAUUSD | range boundary | 20:00 | coin-flip control | 960 | 36% | -0.020 | -0.11 to +0.07 | -19.6 | -0.063 | 0.042 | 54% | 8.5 | +0.014 (466) | -0.053 (494) | -0.07 / +0.07 / -0.06 | -6,676 | no |
