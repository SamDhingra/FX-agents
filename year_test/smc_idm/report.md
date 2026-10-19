# SMC inducement trap → 5m CHoCH → 3m order-block limit (gold), scale-invariant spec

Author's model in the author's own exact definitions (Oct 19 2026), every open point fixed in fxagents/smc_idm.py before any run. Real OANDA bid/ask fills (a limit fills only when the ask/bid actually trades there); R per whole position (50% TP1, 50% TP2) after spread; 2× costs pays one more spread.

Gates: ≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves, better than the coin flip and than the same model without the 1H bias. **Step 1:** the seen sets (2021 → Sep 2026) must clear every gate combined and be positive in each. **Step 2:** only then is the untouched 2016–2020 export opened, once, and judged.

### dev_m1 — seen (step 1): **no pass**

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 14 | 43% | +0.495 | -0.50 to +1.64 | +0.380 | +1.277 | -0.287 | +6.9 | +341 | 86 min |
| coin-flip control | 14 | 21% | -0.367 | -1.00 to +0.48 | -0.482 | +0.267 | -1.000 | -5.1 | -501 | 49 min |
| no HTF filter | 60 | 33% | +0.106 | -0.34 to +0.58 | +0.004 | +0.447 | -0.284 | +6.4 | -390 | 80 min |

Exits: stop 57%, flat_1630 36%, tp2 7%. Long -0.002 (5), short +0.771 (9). Typical stop $7.07 (middle half $4.52–$8.60); typical spread 9% of it; median TP1 3.8R, TP2 3.9R; median hold 86 min.

### holdout_m1 — seen (step 1): **no pass**

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 26 | 27% | -0.399 | -0.80 to +0.13 | -0.530 | -0.300 | -0.558 | -10.4 | -222 | 34 min |
| coin-flip control | 26 | 27% | -0.253 | -0.73 to +0.31 | -0.383 | -0.050 | -0.576 | -6.6 | -105 | 36 min |
| no HTF filter | 112 | 27% | -0.190 | -0.46 to +0.10 | -0.348 | -0.119 | -0.263 | -21.2 | -732 | 26 min |

Exits: stop 73%, flat_1630 15%, tp2 8%, stop_after_tp1 4%. Long -0.483 (15), short -0.286 (11). Typical stop $2.34 (middle half $1.78–$3.01); typical spread 14% of it; median TP1 3.1R, TP2 3.4R; median hold 34 min.

### seen, combined — step 1 gate: **no pass**

| Test | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Total R | Net pips | Median hold |
|---|---|---|---|---|---|---|---|---|---|---|
| **rule** | 40 | 32% | -0.086 | -0.54 to +0.42 | -0.212 | -0.349 | +0.308 | -3.5 | +119 | 57 min |
| coin-flip control | 40 | 25% | -0.293 | -0.69 to +0.15 | -0.418 | -0.190 | -0.446 | -11.7 | -605 | 45 min |
| no HTF filter | 172 | 29% | -0.087 | -0.32 to +0.16 | -0.225 | -0.203 | +0.035 | -14.9 | -1,122 | 46 min |
Setups reaching each stage (rule, longs + shorts, seen sets): 15m zones (base + FVG) 28,472 → zone tapped 25,831 → with inducement swept 14,453 → in 1H bias + discount 3,501 → 5m CHoCH 556 → with 5m/3m FVG 533 → 3m order block found 416 → limit filled and taken 40

**Step 1 failed — old_m1 was NOT opened** and stays untouched.

