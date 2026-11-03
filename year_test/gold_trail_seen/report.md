# Gold overnight breakout: trailing stop (seen, 2021-01-01 → 2026-10-01)

Registered Nov 3 2026 before running (research/gold_trail/PREREGISTRATION_2026-11-03.md). Same entries as the gold_breakout book (00–07 GMT+3 range, 1% stop, flat 20:00 GMT+3, real OANDA bid/ask); only the stop after entry changes. Paired per trade against the rule without a trail.

No trail (the book today): 1461 trades, 50% win, avg +0.055R, net 29,999 pips.

| variant | verdict | trades changed | win | avg R | change vs no trail (95% range) | halves | net pips |
|---|---|---|---|---|---|---|---|
| trail 0.5R after +0.5R (primary) | **no** (95% range above 0, both halves > 0) | 506 of 1461 | 58% | +0.028 | -0.027 (-0.050 to -0.006) | -0.023 / -0.031 | 17,133 |
| break-even at +0.5R | info | 260 of 1461 | 40% | +0.034 | -0.021 (-0.039 to -0.004) | -0.014 / -0.028 | 18,719 |
| trail 1R after +1R | info | 85 of 1461 | 51% | +0.051 | -0.004 (-0.017 to +0.008) | +0.004 / -0.013 | 26,059 |
| chandelier 3 × ATR15 | info | 1415 of 1461 | 33% | -0.009 | -0.064 (-0.101 to -0.034) | -0.044 / -0.085 | 392 |

**trail_half does not pass → the vault is not touched; the book keeps its rule.**

### Trades that reached +0.5R and then closed below 0 without a trail (the Nov 3 pattern)

- 119 trades were turned from a loss into a smaller loss or a gain by the 0.5R trail (avg -0.44R → +0.23R).
- 25 trades made ≥ 2R without a trail; with it they made +0.94R on average instead of +2.68R.
