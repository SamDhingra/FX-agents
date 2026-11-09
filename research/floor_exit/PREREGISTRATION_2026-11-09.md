# Early exit when the pullback's own floor breaks (ICT OTE, DTFX Zone): pre-registration (Nov 9, 2026, before any run)

## Source

Astra's exit review (Nov 9 2026), "the loss-side test: the original pullback has failed".

Both setups enter only on a pullback that has not closed beyond a "floor":
- **ICT OTE:** the 79% retracement of the impulse leg.
- **DTFX Zone:** the 85% retracement.

The protective stop sits farther away, beyond the leg's origin. The hypothesis is that a completed candle closing
beyond that same floor, while the trade is losing, means the setup has failed, so exiting then beats waiting for the
full stop.

**Prior, written now.** Five earlier exit tests failed. The closest one, M15 invalidation (Oct 28), changed 1,649 of
10,724 trades by −0.002R. The atlas (Nov 6) found these setups at about zero edge before costs. Rejection is the
expected outcome.

## Cohort

- **Generation.** Every `ict_ote` and `dtfx_zone` entry the research engine (`research.run_job`) produces, with:
  - default parameters, on XAUUSD, NDQ and US30, on 5m and 15m (the hourly pick's timeframes);
  - the live filters: bias rule (side × score ≥ 0.25), `sessions.entry_windows`, the late cut-off, news blackouts and
    the exact live-window check;
  - one trade at a time per setup × instrument × timeframe.
- **Replay.** Each entry is replayed by `research.simulate_live` on 1-minute mid bars with the real bid/ask spread
  of every minute, under the **standard exit profile as configured today**:
  - half at +1R, stop to +0.1R;
  - runner trailed, the 45-minute stall rule, the runner target at +2R;
  - 240-minute hold, 15:50 flatten.
- **Engine check.** The replay must reproduce the engine's recorded R on ≥ 98% of entries, or nothing is judged.

**Deviation from the source.**
- This tests the raw setups at default parameters with the live filters, not the hourly pick's own selections and
  learned parameters. Those can't be rebuilt from history; Astra's fallback is forward logging only.
- A pass here therefore still needs a forward paired check on the practice account before any change.

## The floor F

- **Source.** The exact price the setup computed at signal time is recorded as `features["floor"]`. It is frozen and
  never redrawn:
  - long: F = leg high − fib_floor × (leg high − leg low);
  - shorts mirror it.
- **Eligibility.** The rule applies only when F lies strictly between the actual fill and the stop actually used
  (after the engine's minimum-stop widening). Otherwise the trade keeps baseline management and the reason is counted.

## Candidate rule `floor_exit` (one variant, nothing tuned)

The rule acts only while the position is open and before the first target has been reached.

1. **Candles watched.** Only completed entry-timeframe mid candles that started at or after the fill, i.e. candle
   i+1 onward, since the fill is at the close of signal candle i.
2. **Trigger.** At the first such candle whose close is beyond F:
   - for a long, close < F; for a short, close > F (equality does not count);
   - AND the trade is losing at that moment on its executable side (bid for a long, ask for a short) against the
     actual fill.
3. **Exit.** Everything closes at the next minute's open on the executable side, not at F and not at the candle
   close.
4. **Priorities.** A stop, target or time exit that happens first keeps priority. Nothing else changes: no new stop,
   no adds.

## Controls

- **Primary arm.** Baseline is the unchanged policy; d = R(floor_exit) − R(baseline) per entry, zero for entries the
  rule does not change.
- **Placebo.**
  - Each eligible trade's depth is (fill − F) ÷ (fill − stop), on its side.
  - Depths are permuted among eligible trades within strata of setup × instrument × side × timeframe × calendar half.
  - The identical rule (same losing-trade condition, same candle closes, same next-minute exit) is re-run at the
    permuted level.
  - There are 10,000 permutations, seed 20261109.
  - p = the share of permutations whose mean d (over all cohort entries) is ≥ the real mean d.

## Gates (all required)

1. at least 90% of cohort entries reconstructable (engine match and a recorded floor);
2. at least 100 changed trades, with at least 30 in each half;
3. the 95% range of the mean d above 0, using circular 5-weekday blocks over all weekdays of the period, with trades
   that have no change kept as zero;
4. mean d above 0 in both halves;
5. mean d above 0 at 2× spread (both arms re-run with the spread doubled around the same mid);
6. placebo p < 0.05;
7. the share of entries finishing at or below −1R falls.

**Shown, never a pass:**
- mean of the worst 5% of R;
- maximum drawdown of cumulative R;
- R saved on trades the rule cut that would have hit the stop;
- R lost on trades it cut that would have recovered;
- by setup, instrument, timeframe and side;
- the baseline's own average R.

## Stages

| stage | data | split | rule |
|---|---|---|---|
| seen | 2021-01-01 → 2026-09-30 (`holdout_m1` + `dev_m1`) | 2023-11-17 | all gates |
| vault | 2016-01-01 → 2020-12-31 (`old_m1` + `old_m1_idx`), once for this family | 2018-07-01 | only after a seen pass |

## What follows

- **A failure at either stage** closes the floor exit. No other depth, faster candle or other lookback is tried on
  these results.
- **A vault pass** starts forward paired shadow logging on the practice account (what the rule would have done, with
  no trades changed), read once after 100 changed entries.
- **Any pass** is no permission to trade a still-negative setup. Adoption needs the managed setup itself to be
  positive under the project's gates.

## Outcome (Nov 9, 2026): fails on seen; the floor exit is closed (vault not opened)

| entries | changed | baseline avg R | floor exit avg R | mean d (95% range) | halves | 2× spread | placebo p | at ≤ −1R |
|---|---|---|---|---|---|---|---|---|
| 15,768 | 4,357 | −0.070 | −0.072 | −0.003 (−0.009 to +0.004) | −0.006 / +0.001 | −0.004 | 0.891 | 44.1% → 22.8% |

- **The engine check passed:** the replay reproduced 100% of the engine's results, and every entry had its floor
  recorded.
- **Full losses roughly halved, but nothing was gained in total.**
  - Cutting 3,364 trades that would have been stopped saved +944R.
  - Cutting 993 trades that would have recovered lost −984R.
- **The setup's own floor is no better than a random depth:** placebo p = 0.89.
- **The baseline itself loses −0.07R per entry.** Both setups are negative on every instrument and timeframe, as the
  atlas found.
