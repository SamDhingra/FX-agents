# Trailing stop for the gold overnight breakout: pre-registration (Nov 3, 2026, before any run)

## Why

On Nov 3 the `gold_breakout` paper book's trade was about 250 pips (≈ $25, about 0.6%) in profit, then closed at a
loss. Sam asked for a trailing stop.

One day can't settle it. A trailing stop that saves such a day also cuts the big trend days that the breakout's profit
depends on. Mechanical trailing made C10 worse (−0.05R).

## Baseline: the rule exactly as the book trades it

`fxagents/breakout_test.py`, the author's defaults:
- the range is the high/low of 00:00–06:59 GMT+3;
- from 07:00, a buy stop at the range high and a sell stop at the range low, one trade a day;
- the stop is 1% of the fill price;
- there is no target;
- the trade is flat at 20:00 GMT+3.

Fills use the real OANDA bid/ask.

## Variants (each changes only the stop after entry)

- **R:** 1R = the initial stop distance (1% of entry).
- **Progress:** measured on the exit side, i.e. the best bid for longs and the best ask for shorts.
- **Order within a minute:** the stop is checked with the level set before that minute, then moved. A minute's high
  never protects the same minute's low.

| variant | rule | role |
|---|---|---|
| `trail_half` | once the trade is +0.5R, trail the stop 0.5R behind the best price (only toward profit) | **primary** |
| `be_half` | once +0.5R, move the stop to the entry price (break-even), once | information |
| `trail_1r` | once +1R, trail 1R behind the best price | information |
| `chandelier` | trail 3 × ATR(14) of completed 15-minute mid candles behind the best price, from entry | information |

## Gates

Paired per trade, d = R(variant) − R(baseline), on 2021-01-01 to 2026-09-30 (the `holdout_m1` + `dev_m1` exports).
`trail_half` passes only if all of these hold:

- at least 100 trades changed;
- the mean d is above 0 with its 95% range above 0 (bootstrap over 5-day blocks of trading days);
- both calendar halves above 0 (split at 2023-11-17).

Spread is paid identically by both, so "2× costs" doesn't change d and is not a gate. Each variant's own average R and
its net pips are shown alongside.

**Vault.** If `trail_half` passes, it is judged once on 2016–2020 (`old_m1`).

## What follows

- **If it is confirmed:** the `gold_breakout` paper book gets the trailing stop. Its earlier record stays labelled as the
  no-trail version.
- **If not:** the book keeps its rule.

Today's trade is not part of either period.
