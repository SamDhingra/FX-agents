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

## Outcome (Nov 3, 2026): fails on 2021–2026; the vault is not touched; the book keeps its rule

No trail: 1,461 trades, 50% win, +0.055R, 29,999 pips.

| variant | changed | win | avg R | vs no trail (95% range) | halves | net pips |
|---|---|---|---|---|---|---|
| trail 0.5R after +0.5R (primary) | 506 | 58% | +0.028 | −0.027 (−0.050 to −0.006) | −0.023 / −0.031 | 17,133 |
| break-even at +0.5R | 260 | 40% | +0.034 | −0.021 (−0.039 to −0.004) | −0.014 / −0.028 | 18,719 |
| trail 1R after +1R | 85 | 51% | +0.051 | −0.004 (−0.017 to +0.008) | +0.004 / −0.013 | 26,059 |
| chandelier 3 × ATR15 | 1,415 | 33% | −0.009 | −0.064 (−0.101 to −0.034) | −0.044 / −0.085 | 392 |

The trail did turn 119 Nov-3-style givebacks from −0.44R into +0.23R on average. It also cut the 25 trades of 2R or more
from +2.68R to +0.94R. The strategy's edge is in those few large days, so every trail tested lowers it. This closes the
trailing-stop family for this book.
