# Trend rules held overnight, NDQ-only SuperTrend, SuperTrend inside EMA21/RSI55: pre-registration (Nov 2, 2026, before any run)

Sam's three questions, asked after the SuperTrend + EMA + RSI result (research/supertrend):

1. **Hold, don't flatten.** Do the current EMA21/RSI55 rule and the SuperTrend rule work on higher timeframes, held
   overnight and over weekends instead of being flattened at 15:50? Stops get bigger in points, but results are
   measured in R, so the size of the stop doesn't change the verdict.
2. **NDQ only.** Does the SuperTrend rule hold on NDQ alone? NDQ was +0.067R on 2021–2026, but it was picked after
   seeing that run, so it gets one judgement on unseen data.
3. **Combining.** Does adding SuperTrend to the current EMA21/RSI55 rule help? Sam's forward record shows EMA21/RSI55
   doing well on gold around 06:00 New York, so that is tested too.

Same engine as research/supertrend:
- OANDA bid/ask 1-minute data with the real spread of every minute;
- entries at the signal candle's close (buy at the ask, sell at the bid);
- stops checked on the 1-minute bid/ask, and a gap fills at the open;
- one trade at a time per instrument;
- 2× costs pays one more full spread.

**Gates for every primary**:
- at least 100 trades;
- average R above 0;
- 95% range above 0 (5-day blocks);
- average R above 0 at twice the spread;
- positive in both calendar halves (seen split 2023-11-17);
- better than the primary's own control (listed with each primary).

A primary that passes on the seen period (2021-01-01 to 2026-09-30) is judged once on 2016-01-01 to 2020-12-31. Seven
primaries are tested at once, so about one could pass the seen period by luck; the single vault run is what decides.
No trading change follows before the Nov 5 review. A rule that passes both becomes a paper book first.

## Rules

**SuperTrend rule (ST).** SuperTrend(10, 3) and EMA 200, as in research/supertrend.
- **Long:** the first candle where SuperTrend is up, the close is above EMA 200 and RSI(14) is in 50–70. Short is the
  mirror (RSI in 30–50).
- **Stop and trail:** at the SuperTrend line. Skip the trade if the stop is closer than 0.3 or farther than 4 × ATR(10).
- **Exit:** a close beyond the line (a flip).

**EMA21/RSI55 rule (ER)**, exactly as the paper book trades it.
- **Long:** a candle closes above EMA21, the previous candle closed at or below it, and RSI(14) > 55. Short is the
  mirror (closes below, RSI < 45).
- **Exit:** the first candle that closes back across EMA21.
- **Stop:** a protective stop 3 × ATR(14) from entry. This also defines 1R.

## Part 1: held trades (no session flatten), NDQ + gold + US30 pooled

- **Entries:** any hour the market is open.
- **Holding:** through the daily break and weekends until the rule's own exit or its stop.
- **Financing:** OANDA charges CFD financing for every night held, and the bot has no history of the actual rates, so
  a cost of **5% a year of the position's value** is charged. That's one night per 17:00 NY rollover, with Friday's
  rollover counted as three nights. Results at 0% and 10% are shown alongside.

| primary | rule | candles | control |
|---|---|---|---|
| `hold_st_1h` | ST | 1 hour | random entry times in the SuperTrend direction, same stop and exit |
| `hold_st_4h` | ST | 4 hours | same |
| `hold_er_1h` | ER | 1 hour | random entry times, side = the close's side of EMA21, same stop and exit |
| `hold_er_4h` | ER | 4 hours | same |

## Part 2: NDQ only, SuperTrend rule, unchanged (`ndq_st_15m`)

- The research/supertrend rule exactly as run: 15-minute candles, entries 03:00–15:30, flat at 15:50.
- NDQ only, judged **once, directly on 2016-01-01 to 2020-12-31**, because 2021–2026 is where the idea came from.
- Gates as above. The control is random timing on NDQ.

## Part 3: SuperTrend inside EMA21/RSI55 (15-minute, intraday, as the paper book)

- Entries on candles closing 02:00–15:30 New York.
- Flat at 15:50.
- Gold and US30, the paper book's instruments.

| primary | what | control (must beat) |
|---|---|---|
| `er_st_filter` | ER, but only when SuperTrend points the same way as the entry | plain ER (`er_base`) over the same period |
| `er_gold_06` | plain ER on **gold**, entries on candles closing 06:00–06:59 NY | plain ER on gold at all other hours |

`er_gold_06` comes from Sam's forward paper record (from October 2026). That record is after the seen period, so
2021–2026 is a fair test of it.

**Shown, not judged:**
- plain ER;
- ER with SuperTrend's stop, trail and exit instead of the EMA exit;
- ER by instrument × entry hour;
- ER with the SuperTrend filter by instrument × entry hour.
