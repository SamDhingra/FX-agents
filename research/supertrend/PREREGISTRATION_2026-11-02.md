# SuperTrend + EMA + RSI: pre-registration (Nov 2, 2026, before any run)

Sam asked to test the common combination of a SuperTrend line, an EMA trend filter and RSI momentum. The rules are the
textbook version: settings are the standard published ones, none is tuned on our data, and nothing below changes
after a run.

## Indicators (on 15-minute candles built from 1-minute mid prices)

- **SuperTrend (10, 3):** ATR is Wilder's, period 10. The bands are HL2 ± 3 × ATR, with the usual carry-forward rule:
  the lower band only rises while the trend is up, and the upper band only falls while it is down. The trend flips
  when a candle closes beyond the active band.
- **EMA 200** of the close.
- **RSI 14**, Wilder's.

## Primary rule `st_ema_rsi` (the only one that can pass)

- **Long.** On a closed candle, all three are true:
  - SuperTrend is up (the close is above the line).
  - The close is above EMA 200.
  - RSI is between 50 and 70.
  
  The trade fires on the **first** candle where all three are true, after a candle where at least one was not. Short
  is the mirror: SuperTrend down, close below EMA 200, RSI from 30 up to (not including) 50.
- **Entry hours.** Only candles closing 03:00–15:30 New York.
- **Entry fill.** At the close of the signal candle, paying the real spread: longs buy at the ask, shorts sell at the
  bid of that minute.
- **Stop.** The SuperTrend line on the signal candle. The trade is skipped if that is closer than 0.3 × ATR or further
  than 4 × ATR.
- **Trailing stop.** After each later 15-minute close, the stop moves to the new SuperTrend line, only toward profit.
- **Exits:**
  - the stop is touched on the 1-minute bid (longs) or ask (shorts), filled at the stop or at a worse opening price;
  - a 15-minute close beyond the SuperTrend line (a flip), filled at that minute's bid or ask;
  - 15:50 New York at the latest.
- **Positions.** One trade at a time per instrument.
- **Instruments.** NDQ, gold and US30 are pooled. The OANDA bid/ask 1-minute data are the same files every recent
  test used.
- **R.** Profit or loss after the spread, divided by the entry-to-stop distance. "2× costs" pays one more full spread.

## Gates

**Seen period:** 2021-01-01 to 2026-09-30, with calendar halves split on 2023-11-17. The primary rule passes only if it
meets all of these:

1. at least 100 trades;
2. average R above 0;
3. 95% range above 0 (bootstrap over 5-day blocks of trading days);
4. average R above 0 at twice the spread;
5. positive in both calendar halves;
6. better than its **random-timing control**: the same instruments, hours, stop at the SuperTrend line, trailing and
   exits, but entered at random 15-minute closes in the trend's direction (one control trade per real trade, fixed
   seed).

**Vault.** If, and only if, the primary rule passes on the seen period, it is judged once on 2016-01-01 to 2020-12-31
with the same gates. A vault run refuses to repeat, and no other rule goes to the vault.

## Shown, not judged

None of these can rescue a failed primary:

- each instrument on its own;
- the same rule on 5-minute and 1-hour candles;
- SuperTrend flips alone, without EMA and RSI (do the filters add anything?);
- an RSI exit (leave when RSI crosses back through 50);
- results by hour.

## What follows

**No trading change before the Nov 5 review.** A rule that passes both the seen period and the vault becomes a paper
book first.

## Outcome (Nov 2, 2026, seen period): does not pass, the vault is not touched

| | trades | avg R | 95% range | 2× costs | halves | random-timing control |
|---|---|---|---|---|---|---|
| st_ema_rsi (pooled) | 9,508 | +0.029 | −0.007 to +0.062 | −0.010 | +0.048 / +0.009 | +0.000 |

The rule beats random timing, the halves are positive and the trade count is large. It fails because the 95% range
touches 0 and twice the spread turns it negative.

These figures are shown only, so they are not evidence:

| slice | trades | avg R | 95% range | 2× costs | halves |
|---|---|---|---|---|---|
| NDQ alone | 3,242 | +0.067 | +0.009 to +0.123 | +0.035 | +0.095 / +0.036 |
| US30 alone | | +0.015 | | | |
| Gold alone | | +0.003 | | | |
| SuperTrend alone, no EMA or RSI | | +0.021 | | | |
| 5-minute candles | | −0.023 | | | |
| 1-hour candles | | −0.015 | | | |
| RSI exit | | +0.004 | | | |

NDQ was picked after looking at these results, so its figure is a hypothesis, not a result. If it is tested, it gets a
new registration and is judged once on 2016–2020.
