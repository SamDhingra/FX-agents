# CISD on dev_m1

Rules fixed before testing (fxagents/cisd_test.py docstring): Set A = sweep of PDH/PDL, Asian range or (NY) London range → CISD (close beyond the open of the first candle of the last delivery series, within 12 candles) → market entry, stop beyond the sweep extreme + 0.1 ATR, 2R target, skip if stop < 4 spreads, one trade per window. Set B adds a 1h-CISD bias and an FVG-midpoint limit entry. Real OANDA bid/ask fills; R includes the spread.

Pass = ≥100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs. **0 of 24 cells pass.** The coin-flip control takes the same trades with a random direction: CISD only adds something if it beats its control.

| Symbol | Rule | TF | Window | Trades | Win | Avg R | 95% range | Total R | Avg R 2× costs | Spread (R) | Hit 2R | Net pips | Pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | Set A | 5min | London | 96 | 29% | -0.132 | -0.39 to +0.14 | -12.7 | -0.222 | 0.090 | 28% | -1,581 | no |
| XAUUSD | coin-flip control | 5min | London | 96 | 27% | -0.187 | -0.44 to +0.08 | -18.0 | -0.277 | 0.090 | 27% | -1,043 | no |
| XAUUSD | Set A | 5min | NY | 157 | 45% | +0.005 | -0.17 to +0.18 | +0.7 | -0.046 | 0.050 | 17% | +1,521 | no |
| XAUUSD | coin-flip control | 5min | NY | 157 | 39% | -0.029 | -0.20 to +0.15 | -4.6 | -0.079 | 0.050 | 17% | -580 | no |
| XAUUSD | Set A | 1min | London | 143 | 30% | -0.098 | -0.34 to +0.13 | -14.0 | -0.228 | 0.130 | 30% | -1,632 | no |
| XAUUSD | coin-flip control | 1min | London | 143 | 30% | -0.102 | -0.34 to +0.15 | -14.6 | -0.232 | 0.130 | 29% | -739 | no |
| XAUUSD | Set A | 1min | NY | 221 | 29% | -0.148 | -0.31 to +0.02 | -32.7 | -0.247 | 0.098 | 26% | -2,405 | no |
| XAUUSD | coin-flip control | 1min | NY | 221 | 30% | -0.104 | -0.28 to +0.08 | -23.0 | -0.202 | 0.098 | 28% | -1,437 | no |
| XAUUSD | Set A | 15min | London | 59 | 34% | -0.108 | -0.40 to +0.22 | -6.4 | -0.166 | 0.058 | 22% | -1,311 | no |
| XAUUSD | coin-flip control | 15min | London | 59 | 47% | +0.246 | -0.10 to +0.62 | +14.5 | +0.189 | 0.058 | 29% | +3,299 | no |
| XAUUSD | Set A | 15min | NY | 77 | 52% | +0.157 | -0.04 to +0.36 | +12.1 | +0.124 | 0.033 | 9% | +2,052 | no |
| XAUUSD | coin-flip control | 15min | NY | 77 | 53% | +0.094 | -0.14 to +0.33 | +7.2 | +0.061 | 0.033 | 8% | +1,218 | no |
| XAUUSD | Set B | 5min | London | 3 | 33% | +0.000 | -1.00 to +2.00 | +0.0 | -0.116 | 0.116 | 33% | +2 | no |
| XAUUSD | Set B | 5min | NY | 8 | 25% | -0.250 | -1.00 to +0.80 | -2.0 | -0.326 | 0.076 | 25% | -397 | no |
| NDQ | Set A | 5min | London | 149 | 38% | +0.107 | -0.12 to +0.35 | +16.0 | +0.041 | 0.066 | 36% | +215 | no |
| NDQ | coin-flip control | 5min | London | 149 | 32% | -0.059 | -0.27 to +0.16 | -8.8 | -0.125 | 0.066 | 31% | -38 | no |
| NDQ | Set A | 5min | NY | 229 | 37% | -0.052 | -0.20 to +0.10 | -11.9 | -0.071 | 0.019 | 21% | -2,300 | no |
| NDQ | coin-flip control | 5min | NY | 229 | 38% | -0.011 | -0.16 to +0.14 | -2.5 | -0.030 | 0.019 | 22% | -829 | no |
| NDQ | Set A | 1min | London | 199 | 24% | -0.277 | -0.46 to -0.08 | -55.1 | -0.400 | 0.123 | 24% | -789 | no |
| NDQ | coin-flip control | 1min | London | 199 | 30% | -0.095 | -0.30 to +0.11 | -19.0 | -0.219 | 0.123 | 30% | -650 | no |
| NDQ | Set A | 1min | NY | 320 | 33% | -0.020 | -0.16 to +0.13 | -6.4 | -0.061 | 0.041 | 31% | -773 | no |
| NDQ | coin-flip control | 1min | NY | 320 | 34% | +0.021 | -0.10 to +0.14 | +6.6 | -0.020 | 0.041 | 32% | -972 | no |
| NDQ | Set A | 15min | London | 87 | 45% | +0.292 | +0.00 to +0.59 | +25.4 | +0.245 | 0.046 | 40% | +1,750 | no |
| NDQ | coin-flip control | 15min | London | 87 | 37% | +0.087 | -0.18 to +0.36 | +7.6 | +0.041 | 0.046 | 33% | +858 | no |
| NDQ | Set A | 15min | NY | 137 | 46% | +0.056 | -0.13 to +0.24 | +7.6 | +0.043 | 0.013 | 13% | +1,327 | no |
| NDQ | coin-flip control | 15min | NY | 137 | 47% | +0.111 | -0.06 to +0.29 | +15.3 | +0.099 | 0.013 | 17% | +2,124 | no |
| NDQ | Set B | 5min | London | 8 | 50% | +0.500 | -0.62 to +1.62 | +4.0 | +0.384 | 0.116 | 50% | +114 | no |
| NDQ | Set B | 5min | NY | 14 | 43% | +0.039 | -0.59 to +0.76 | +0.6 | +0.022 | 0.017 | 21% | +477 | no |
| US30 | Set A | 5min | London | 184 | 31% | -0.078 | -0.28 to +0.13 | -14.4 | -0.153 | 0.074 | 30% | -263 | no |
| US30 | coin-flip control | 5min | London | 184 | 33% | -0.029 | -0.23 to +0.18 | -5.4 | -0.104 | 0.074 | 32% | +750 | no |
| US30 | Set A | 5min | NY | 214 | 33% | -0.180 | -0.32 to -0.03 | -38.5 | -0.211 | 0.030 | 14% | -6,364 | no |
| US30 | coin-flip control | 5min | NY | 214 | 35% | -0.112 | -0.26 to +0.04 | -24.0 | -0.143 | 0.030 | 15% | -3,709 | no |
| US30 | Set A | 1min | London | 232 | 28% | -0.168 | -0.35 to +0.01 | -38.9 | -0.292 | 0.124 | 28% | -940 | no |
| US30 | coin-flip control | 1min | London | 232 | 26% | -0.212 | -0.39 to -0.03 | -49.1 | -0.336 | 0.124 | 26% | -1,559 | no |
| US30 | Set A | 1min | NY | 276 | 32% | -0.074 | -0.22 to +0.07 | -20.3 | -0.131 | 0.058 | 28% | +455 | no |
| US30 | coin-flip control | 1min | NY | 276 | 32% | -0.113 | -0.25 to +0.03 | -31.2 | -0.171 | 0.058 | 27% | -2,635 | no |
| US30 | Set A | 15min | London | 103 | 34% | -0.022 | -0.28 to +0.25 | -2.3 | -0.072 | 0.050 | 30% | -374 | no |
| US30 | coin-flip control | 15min | London | 103 | 25% | -0.264 | -0.49 to -0.01 | -27.2 | -0.314 | 0.050 | 23% | -983 | no |
| US30 | Set A | 15min | NY | 131 | 40% | -0.107 | -0.26 to +0.05 | -14.0 | -0.132 | 0.025 | 5% | -2,327 | no |
| US30 | coin-flip control | 15min | NY | 131 | 41% | -0.142 | -0.31 to +0.03 | -18.6 | -0.167 | 0.025 | 5% | -2,990 | no |
| US30 | Set B | 5min | London | 16 | 19% | -0.438 | -1.00 to +0.25 | -7.0 | -0.548 | 0.111 | 19% | -390 | no |
| US30 | Set B | 5min | NY | 19 | 32% | -0.207 | -0.69 to +0.36 | -3.9 | -0.227 | 0.019 | 11% | -50 | no |
