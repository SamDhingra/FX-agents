# Gold breakout: add when a pullback resumes, armed at +0.5R: pre-registration (Nov 3, 2026, before the vault run)

## Where it comes from

`add_early` was an information variant in research/gold_more. On 2021 to Sep 2026 it gave:
- 406 adds, 43% won;
- +0.051R per add (in the day's R);
- 95% range −0.023 to +0.126;
- halves +0.101 / +0.014;
- +0.025 at 2× costs.

It looked best after the results were seen, so those years can't judge it. It gets **one judgement on 2016–2020**
(`old_m1`), which no gold breakout management test has used.

## Rule `add05` (exactly gold_more's `add_early`; code: `fxagents.gold_more.add_on(..., arm_r=0.5, stop_kind="ext")`)

**Entries.** The same as the `gold_breakout` book:
- the range is 00:00–06:59 GMT+3;
- stop orders sit at the range, one trade a day;
- the stop is 1% (= 1R);
- everything is flat at 20:00 GMT+3;
- fills use the real OANDA bid/ask.

**Arming**
- The trade has reached +0.5R at its best.
- Price has then pulled back at least 0.5R from that best.
- A new best resets the arming.

**Signal**
- A completed 15-minute mid candle closes in the trade's direction and beyond the previous candle's high (longs) or low
  (shorts).

**The add**
- **Entry.** At the next minute's open.
- **Stop.** The pullback extreme, never closer than 0.25R.
- **Size.** It risks 0.5R of the day.
- **Exit.** At its stop, at 20:00, or when the original trade is stopped.
- **Limits.** One add a day.

## Gates (2016-01-01 to 2020-12-31, judged once)

The result is d = the add's result per add. All of these are required:
- at least 100 adds;
- the 95% range of the mean d above 0 (5-day blocks);
- both halves above 0 (split 2018-07-01);
- still above 0 at 2× costs (one more spread per add).

## What follows

- **If it is confirmed:** a separate paper book `gold_breakout_add` runs beside `gold_breakout`, the same trades plus the
  add, and the review compares them.
- **If it is not confirmed:** adding on the resumption is closed for this book.

On 2021–2026 it is worth about +0.014R per day across all days, a small gain even if real.
