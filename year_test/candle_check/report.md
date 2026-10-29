# Entry vs candle close (journals)

Each trade's entry time against the close of the candle its setup fired on (the drawing's signal bar + the setup's timeframe). **Early** = entered before that candle closed. Trades before Oct 19 2026 have no drawing and can't be checked.

| book | checked | entered before the setup candle closed | median delay after close | max delay | 3m/5m entries while the 15m candle was still forming | not checkable |
|---|---|---|---|---|---|---|
| live | 48 | **0** | 6 s | 19 s | 24 of 35 | 61 |
| c10_afternoon | 0 | — | — | — | — | 4 |
| ema21_rsi55 | 0 | — | — | — | — | 46 |
| gold_breakout | 0 | — | — | — | — | 11 |
| h1_vol_trend | 0 | — | — | — | — | 2 |
| playbook | 64 | **0** | 6 s | 19 s | 35 of 47 | 52 |
| playbook_regime | 22 | **0** | 6 s | 17 s | 12 of 15 | 10 |

**No entry was made before its own setup candle closed.** A 3m / 5m entry made while the 15-minute candle is still forming is how the setups are designed (their own candle has closed); whether waiting for the 15-minute close helps was tested on Oct 28 (m15_timing A: the gain came from waiting itself, a random later entry did as well).
