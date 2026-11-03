# Gold breakout: no-progress exit, and add on the resumption after a pullback (pre-registration, Nov 3, 2026, before any run)

## Why

Two ideas from Sam after the trailing-stop and ladder tests (research/gold_trail, research/gold_ladder):

- **The losing days.** Cut trades that go nowhere early, instead of holding them to the 1% stop or to 20:00.
- **The big days.** They pull back about 1R in the middle (median 0.98R, 24 of 25) and then resume. The idea is to add
  to the position when the pullback turns back into the trend.

Both are judged separately against the book as it trades today. The entries are the same as the `gold_breakout` book:
- the range is 00:00–06:59 GMT+3;
- stop orders sit at the range high and low, one trade a day;
- the 1% stop is 1R;
- everything is flat at 20:00 GMT+3;
- fills use the real OANDA bid/ask.

## A. `noprog3h`: no-progress exit (primary for A)

- **Rule.** 3 hours after entry, if the trade's best gain so far has never reached +0.5R, close it at that minute's open
  (the bid for longs, the ask for shorts).
- **Otherwise** it is left exactly as now, with the 1% stop and the 20:00 close.
- **Progress** is measured on the exit side, minute highs and lows, up to the minute before the check.

Information (never a pass):
- `noprog2h`: the same rule at 2 hours.
- `noprog4h`: the same rule at 4 hours.
- `under3h`: at 3 hours, close the trade if price is below the entry (above it for a short).

**Gates.** d = R(rule) − R(today) per day. A rule passes only if all of these hold:
- at least 100 days changed;
- the 95% range of the mean d is above 0 (5-day blocks);
- both halves are above 0 (split at 2023-11-17).

The rule only removes time in the market and adds no trades, so costs are unchanged.

## B. `add_resume`: add when a pullback resumes (primary for B)

**Arming**
- The day's trade is open and has reached +1R at its best.
- Price has then pulled back at least 0.5R from that best.
- The pullback extreme is the lowest bid (longs) or the highest ask (shorts) since the best.
- A new best resets the arming.

**Signal**
- While armed, a completed 15-minute mid candle closes in the trade's direction and beyond the previous 15-minute
  candle's extreme. For a long, the close is above the open and above the previous candle's high; for a short, the
  close is below the open and below the previous candle's low.

**The add**
- **Entry.** At the next minute's open (the ask for longs, the bid for shorts).
- **Stop.** Its stop is the pullback extreme, but never closer than 0.25R from the add's entry.
- **Size.** It risks 0.5R of the day: its result is 0.5 × (exit − add entry) ÷ (add entry − add stop), in the day's R.
- **Exit.** It is closed at its stop or at 20:00. If the original trade is stopped out, the add's stop is already above
  the original stop, so it is closed by then.
- **Limits.** One add a day, and only while the original trade is open. It is first checked for its stop from the
  minute after its entry.

**Gates.** d = the add's result per day (0 on days without an add). `add_resume` passes only if all of these hold:
- at least 100 adds;
- the 95% range of the mean d over adds (5-day blocks) is above 0;
- both halves are above 0;
- it is still above 0 at 2× costs, with one more spread charged per add.

Information (never a pass):
- `add_early`: arming after +0.5R instead of +1R.
- `add_stop0`: the add's stop at the day's original stop, risking 0.5R.

## Vault

Each primary that passes is judged once on 2016–2020 (`old_m1`), on its own.

## What follows

- **If a primary is confirmed on 2016–2020:** it runs as a separate shadow paper book beside `gold_breakout`.
- **If not:** the book keeps its rule.

A diagnostic is also shown: how many of the 25 days of ≥ 2R had reached +0.5R within 2, 3 and 4 hours (the days a
no-progress exit would have cut).
