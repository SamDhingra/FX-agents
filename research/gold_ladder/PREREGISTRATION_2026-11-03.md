# Gold breakout "ladder": partial ratchet, runner and one re-entry: pre-registration (Nov 3, 2026, before any run)

## Why

The plain trailing stop (research/gold_trail) lowered the gold breakout's edge. On the 25 days of 2R or more it cut the
average from +2.68R to +0.94R. Sam proposed a management that keeps a runner and re-enters after a false reversal.

This file fixes his idea into exact rules before anything runs. It also adds a diagnosis of what the big days actually
did, which answers his question of whether they pulled back and resumed, or whether the trail was applied wrongly.

## Entries

The same as the `gold_breakout` book and the trailing test:
- the range is 00:00–06:59 GMT+3;
- stop orders sit at the range high and low, one trade a day;
- the initial stop is 1% of entry (= 1R);
- everything is flat at 20:00 GMT+3;
- fills use the real OANDA bid/ask.

## Scale

The plan is written in pips: 100 pips is $10 on gold. Gold has been anywhere from about $1,700 to over $4,000 since 2021,
so a fixed 100 pips is a very different move in different years. The primary therefore uses one step = 0.25R, which is
about 100 pips at today's price of roughly $4,100 (1R ≈ 410 pips). The literal fixed-pip version is shown as
information.

## Primary rule `ladder`

The day's entry is split into two half-size legs, P and R. Progress for a leg is measured from its own entry, on the
exit side (the bid for longs, the ask for shorts).

**Leg P (partial)**
- It starts with the initial stop.
- Once it has gained ≥ 1 step, its stop moves to +½ step.
- Each further full step raises the stop by ½ step: stop = entry + ½ step × floor(best gain ÷ step). That gives +50 at
  +100 pips and +100 at +200 pips, as in the plan.
- The stop never moves back.

**Leg R (runner)**
- It keeps the initial stop and is flat at 20:00. It is not ratcheted.

**Setup broken**
- A completed 15-minute mid candle closes back inside the range: for a long, the close is below the range high; for a
  short, it is above the range low.
- From then on, every open leg that is in profit has its stop raised to its entry (break-even), or to its ratchet level
  if that is higher.
- Every open leg that is not in profit exits at the next minute's open.
- No re-entry is allowed after the break.

**One re-entry (leg E, half size)**
- It is allowed only once leg P has been stopped out in profit, the setup is not broken, and there has been no earlier
  re-entry that day.
- It opens when price comes back to P's exit level, meaning the reversal was false: for a long, the ask reaches it; for
  a short, the bid does.
- The fill is that level, or the minute's open if price gaps through.
- Its stop is the day's initial stop price, and it uses the same ratchet as P (measured from E's own entry).
- It is subject to the same setup-broken rule and the same 20:00 close.

**Order within a minute**
- Stops are checked with the levels set before the minute, then levels move.
- A re-entry that opens in a minute is first checked from the next minute.

**Results**
- A day's result is the sum of its legs, each in units of the day's 1R and weighted ½.
- The most a day can risk is 1.5R: P + R + E. This is shown.

## Gates (2021-01-01 to 2026-09-30, `holdout_m1` + `dev_m1`)

Paired per day, d = R(ladder) − R(no management), the book as it trades today. `ladder` passes only if all of these
hold:

- at least 100 days changed;
- the 95% range of the mean d is above 0 (5-day blocks of trading days);
- both halves are above 0 (split at 2023-11-17);
- the mean d is above 0 at 2× costs. The re-entry pays an extra spread; at 2× costs each re-entry is charged one more
  spread.

**Vault.** If `ladder` passes, it is judged once on 2016–2020 (`old_m1`).

## Information (never a pass)

- `ladder_pips`: the literal plan, 100 / 50 pips fixed.
- `ladder_noreentry`: without leg E.
- `ladder_nobreak`: without the setup-broken rule.
- **Big-day diagnosis**, for each no-management trade that made ≥ 2R:
  - the deepest pullback from the running best after first reaching +0.5R, before its final peak, in R;
  - where the 0.5R trail exited;
  - how far price went on afterwards.

## What follows

- **If `ladder` is confirmed on 2016–2020:** it goes on the `gold_breakout` paper book as a separate shadow book first.
- **If it is not confirmed:** the book keeps its rule.
