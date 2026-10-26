## A. What-if questions

Register **two skip checks and one delayed-entry policy: three new trials**. Test each separately on the frozen playbook's **3m/5m entries**, pooled across the available NDQ, US30 and XAUUSD cells. The 15m/30m entries and instrument/setup breakdowns are descriptive; they cannot rescue a failed primary test. Do not combine the checks, select a threshold after seeing results, or add an LLM veto to these tests.

Both checks use the path of minute-ending **mid closes**, not a completed candle's colour, EMA slope, swing labels, or a reconstructed liquidity pattern. They are related to the existing momentum checks, but are not duplicates: A1 can flag a long even when the current 15m candle is green, and A2 is direction-neutral.

**Shared definitions, frozen before testing.** Let `t = trade['ts']`, `s = side`, and `p(t)` be the close of the minute starting at `t−1 minute`. For `L` elapsed minutes:

- `d_L = p(t) − p(t−L)`.
- `P_L = sum(abs(p(u) − p(u−1 minute)))` over the L minute-to-minute changes ending at t.
- `S15` is the **arithmetic mean of 14 true ranges** of consecutive, complete 15m candles ending at or before `t−30 minutes`. Use the immediately preceding completed candle's close for the first true range. Thus the baseline needs 15 complete candles. This is an explicitly defined SMA of true ranges, **not** the repository's Wilder-style ATR.
- All higher-timeframe candles use New York time and `resample(label='left', closed='left')`. The baseline ends before the measured path; the path itself may cross the current 15m candle and uses only completed minutes. Exactly at a 15m boundary, the minute starting at that boundary is excluded.

| Check | Named failure mechanism | Exact yes/no flag | Why these fixed values |
|---|---|---|---|
| **A1 — `opposing_path_v1`** | Entering before a persistent countermove has paused | `s*d_15 <= −0.50*S15` **and** `−s*d_15 >= 0.70*P_15`, with `P_15 > 0` | 15 minutes matches the timing conflict being investigated. A net half of a typical 15m range excludes tiny quote movements. Efficiency 0.70 means at least 85% of absolute minute-close movement was against the trade; a mere red/green candle does not establish that. |
| **A2 — `two_way_chop_v1`** | Taking a directional setup during active back-and-forth movement | `P_30 >= 2.00*S15` **and** `abs(d_30) <= 0.20*P_30` | 30 minutes observes two 15m periods. Two typical 15m ranges of travelled distance distinguishes active movement from a nearly motionless market. Efficiency at most 0.20 means at least 40% of travelled distance occurred in each direction. |

The **14** true ranges provide 3.5 hours of local scale estimation; this is a conventional, unoptimized normalization choice, not a claimed optimum. The baseline's **30-minute** exclusion is the longer of the two observation windows, giving both checks the same normalizer and valid-data cohort. The same constants apply to all three instruments and both sides.

**Missing data is unavailable, not False.** The functions raise `ValueError` for missing/duplicate/out-of-order minutes, non-minute timestamps, invalid OHLC, or a zero baseline. They require a contiguous interval of at most 269 minutes, entirely before t. Do not forward-fill a market closure or catch an exception and classify that trade as kept. Evaluate both checks on the same valid cohort; report unavailable counts by cell, year and hour. Require at least **90%** coverage of the intended primary cohort in each period; otherwise record an inconclusive data failure. This matches the brief's standard that a result needs broad control coverage, and prevents success on a small convenient subset. Validity must use entry-time data only, never trade outcomes.

**Evaluation to freeze with the code.** Retain the brief's three gates: the day-block 95% interval of `mean(kept.r) − mean(flagged.r)` must be strictly above zero; that difference must be positive in both calendar halves; and matched random skipping must have one-sided `p < 0.05`. Require at least **30 flagged and 30 kept** observations per period, as the current judge does; every half must have both groups. Missing groups, failed controls or undefined intervals fail rather than disappear.

Use seen dates **2021-01-01 inclusive to 2026-10-01 exclusive**, with the brief's fixed split at **2023-11-17 00:00 New York**. The vault is **2016-01-01 to 2021-01-01 exclusive**, split at the elapsed-time midpoint of those bounds. Do not derive either split from trade counts or from the dates left after filtering.

For reproducibility, use **10,000** bootstrap draws, seed **20261026**, percentile endpoints **2.5%/97.5%**, and circular moving blocks of **five consecutive New York weekdays**, including zero-trade weekdays. Sample the same day blocks for kept/flagged, all instruments and all cells; this preserves co-movement within each sampled block. Recompute group sums/counts in every draw. Drop a draw only when a required group has zero observations; fewer than **90%** valid draws makes the interval unavailable. Five days preserves a trading week's local clustering without claiming to capture all regime dependence.

For the equal-count random-skip reference, use **10,000** draws, seed **20261027**, preserving the actual number removed within each `(sym, tf, setup, side, hour, calendar_half)` stratum. Sample without replacement within each stratum; compute the kept mean on the same cohort. Use `p = (1 + number(random_kept_mean >= observed_kept_mean)) / 10001`. A stratum with no possible reassignment stays fixed. This prevents a check from appearing useful merely by dropping a different mix of symbols, setups, sides or hours. The permutation reference relies on exchangeability within strata and is **not independent confirmation** of the block-bootstrap result; serial dependence can still affect its calibration. The shared day-block interval remains essential. Report the unstratified existing benchmark only as a diagnostic, not an alternative pass route.

**Current-code integration finding.** At GitHub commit [`32dff4ada7b63a2a25a3f13eee047047b299a128`](https://github.com/SamDhingra/FX-agents/commit/32dff4ada7b63a2a25a3f13eee047047b299a128), [`mtf_whatif.py`](https://github.com/SamDhingra/FX-agents/blob/32dff4ada7b63a2a25a3f13eee047047b299a128/fxagents/mtf_whatif.py) imports `judge` from [`liquidity.py`](https://github.com/SamDhingra/FX-agents/blob/32dff4ada7b63a2a25a3f13eee047047b299a128/fxagents/liquidity.py). That judge still uses the median **trade timestamp**, unstratified individual-trade deletion and a five-observed-day block construction. `LOW_TF` also includes 1m aliases. Its candle builder does not verify minute counts. The separate plugin-engine fixes do not automatically fix this runner. Apply the frozen evaluation above and restrict the primary cohort to `3m/3min/5m/5min`. [`playbook_test.py`](https://github.com/SamDhingra/FX-agents/blob/32dff4ada7b63a2a25a3f13eee047047b299a128/fxagents/playbook_test.py) likewise still describes a second spread as its cost stress and contains a trade-count split; do not label these playbook outputs as using every fix from engine `38440164bbc2` without porting/verifying them. No repository files have been changed here.

## B. Wait instead of skip

**`wait_for_m15_v1`**, one policy, triggered **only by A1**. If A1 is false, retain the original entry. If A1 is true, allow **30 elapsed minutes** for the first subsequently completed 15m candle to close in the trade's direction. Cancel if the original stop is touched or the market has already moved **0.50 original R** toward profit. Keep the original stop price and the original management profile's R multiples, re-anchored to the new actual fill. Full numbered execution steps follow the code blocks.

The 30-minute deadline allows two subsequent 15m closes; it prevents an intraday signal becoming an indefinite standing order. The half-R cancellation avoids chasing a move that has already consumed a material part of its initial opportunity. The new stop distance must lie in **[0.50, 1.50]** times the original filled-entry risk: the lower bound avoids entering almost on the invalidation point, and the upper bound prevents a much wider risk geometry after confirmation. These are research design choices, not measured optima.

**B is a separate trial from A1.** On the same original-trade opportunities, compare (i) original immediate entry, (ii) A1 skip, and (iii) this delayed policy, using original cash-risk units. Cancellations contribute **zero**, not a removed row. Before portfolio interactions, require the delayed policy's paired advantage over **both** immediate entry and A1 skip to have a day-block 95% interval above zero and a positive point difference in each calendar half. Use the same blocks, draws and seed as A. Beating skip establishes that actual delayed fills add value; merely avoiding some original losers does not establish that. Require at least **30 delayed fills** in each period; unknown eligibility or missing original execution metadata makes a comparison unavailable.

Show net expectancy, count and costs of the delayed fills separately, but do not use their conditional win rate as the primary outcome. For B, the equal-count random-skip question is already evaluated for its A1 trigger; a deletion-only p-value cannot validate the changed entry prices. The paired policy comparisons are B's distinct gates.

The row fields listed in the brief do **not** fully specify the original stop, actual fill, quantity or management profile. Retrieve them from the frozen signal/cell and execution record, including the original minimum-stop adjustment. Do not approximate the original stop by multiplying `risk_atr` by an ATR recomputed with a different warmup. The current [`research.simulate_live`](https://github.com/SamDhingra/FX-agents/blob/32dff4ada7b63a2a25a3f13eee047047b299a128/fxagents/research.py) fills at the signal minute's mid close **plus/minus half-spread** and expresses R from that filled price; the brief's shorthand “filled at that price” needs this distinction for a fair delayed-entry comparison.

## C. Your read

- **A slow bias and an immediate entry answer different questions.** A bearish Daily/4H/1H score can coexist with a tradable 15m upswing. Being eventually right is insufficient when the upswing touches the short's protective stop first. This is a horizon mismatch and a first-passage problem, not proof that the higher-timeframe bias is wrong.
- **Persistent pressure could make early fading costly.** Repeated buying or selling may continue while orders are executed. However, a mid-price path does not reveal actual signed order flow. Lillo and Farmer found persistent order signs **and compensating liquidity responses**; their result does not establish predictable 15m CFD returns. A1 is a testable price-path proxy, not an order-flow detector. [Primary paper](https://arxiv.org/abs/cond-mat/0311053).
- **“Multi-timeframe alignment” is a useful trading description, not a validated edge by itself.** The developing 15m candle contains the very 3m/5m price action that produced the signal; the two observations are not independent confirmations. The exact `ts−1 minute` cutoff matters. “Fractal momentum” would overstate what these tests identify.
- **The stop can be wrong for the path even when direction is eventually right.** During active two-way movement, a tight stop or early breakeven move can be hit before the intended excursion occurs. A2 tests whether that environment harms these particular trades. It does not prove that widening stops improves expectancy; wider stops change R, sizing, time exposure and costs together.
- **The opposite can be true for genuine pullback or mean-reversion entries.** Temporary price pressure may reverse, and entering before confirmation can buy a better price. Nagel's equity research connects short-term reversal returns to liquidity provision, with returns varying across conditions; it is not evidence that these OTE entries work on OANDA CFDs. Blanket opposition/chop filters can remove profitable fades. Keep setup breakdowns descriptive and retain the same rules if a fashionable setup disagrees. [Primary publication record](https://gsbpreserve.stanford.edu/view/41388).
- **Waiting has a price.** Confirmation can avoid an ongoing adverse move, but also miss the best entries, raise the distance to a fixed stop, or eliminate winners that leave without a neat candle turn. This is why B needs entry-time replay, cancellation accounting and original-risk normalization, rather than comparing only the trades that eventually filled.

## D. Honest priors

| Frozen trial | Subjective probability of passing seen **and**, if advanced, repeating on 2016–2020; assessed before either run |
|---|---:|
| A1 — `opposing_path_v1` | **12%** |
| A2 — `two_way_chop_v1` | **7%** |
| B — `wait_for_m15_v1` | **8%** |

These are uncalibrated research priors, not estimated win rates, expected returns or probabilities of a profitable live bot. They reflect plausible mechanisms and the poor conversion of earlier plausible filters into evidence. B's entry and management replay has more ways to disappoint than its chart story suggests. The events are dependent; do not add these probabilities.

**I do not currently expect these checks, by themselves, to make the −0.09R playbook profitable.** They may identify a harmful subset while leaving a losing remainder. For a static cohort, if fraction `f` is flagged and `Delta = mean(kept) − mean(flagged)`, then:

`mean(kept) = mean(all) + f * Delta`.

Using the brief's overall −0.09R as an **illustration**, removing 30% requires `Delta > 0.30R` merely to move the retained mean above zero. Equivalently, the removed group must average below −0.30R. A significant +0.10R separation would still leave −0.06R. Recompute this using the actual 3m/5m valid-cohort baseline; −0.09R is not supplied specifically for that subset. Sampling uncertainty and stricter cost stress raise the evidence hurdle further. A fixed-row calculation also cannot predict the trades admitted when a filter frees a busy book.

**Round two is a rejection, not a tuning invitation.** Retire my three entries as submitted. The H4 gold result is compatible with zero and fails doubled costs; its simpler control's better point estimate does not make that control validated. The H1 gold fade was negative and opposite-direction trading was approximately flat, not an established replacement. The prior-edge NDQ proposal did not establish freshness or RSI value. The two gold H4 implementations differ in entries, stops, targets and holding periods, so their difference does **not** isolate 1H versus 4H stop scale. That remains a confounded hypothesis, not a finding worth widening live stops over.

Count all three new policies in the research ledger alongside the four already registered checks. Do not treat A1 and B as independent discoveries: they share a trigger and constitute one counterflow family. **Predeclare vault priority A1, then B, then A2**, choosing the first policy that clears all of its seen gates; run only that frozen policy once on the untouched 2016–2020 playbook cohort. A failed vault ends this round; no fallback or renamed retry on those same exposed trades. This uses fewer vault degrees of freedom than ranking whichever seen point estimate looks best. A1/B share the same family ledger entry; A2 is a separate hypothesis but is not a post-vault fallback.

A seen pass earns a research/paper filter. A vault pass of discrimination alone still does not establish retained profitability. Before any practice-account change, require a full chronological portfolio replay with the actual opportunity stream, shared exposure limits, real bid/ask costs and the existing management; retained policy net expectancy and its day-block 95% interval must be above zero, calendar halves positive, and the full **2× execution-cost** stress positive. Then prospective paper observation can test execution agreement. No live promotion is part of this assignment.

Validation completed: **22 synthetic feature-contract tests passed** on Python 3.12, pandas 2.2.3 and NumPy 2.3.5. They cover future-row exclusion, outcome-field isolation, exact warmup, missing data, thresholds, mirrored directions and daylight-saving transitions. No historical backtest, historical candle-snapshot inspection, observed flag-rate estimate or P&L simulation was performed. The B policy below is a replay specification; its execution simulator has not been implemented or validated here.


**opposing_path_v1.py**

```python
"""Round 3, A1. Frozen 2026-10-26. Research flag; no trading or outcome reads."""
from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"
MINUTE = pd.Timedelta(minutes=1)


def _window(trade: dict, m1: pd.DataFrame):
    """Past-only, complete minute data; errors mean UNAVAILABLE, never 'keep'."""
    t = pd.Timestamp(trade["ts"])
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError("ts must be timezone-aware")
    t = t.tz_convert(NY)
    if t != t.tz_convert("UTC").floor("min").tz_convert(NY):
        raise ValueError("ts must be a minute boundary")
    side = float(trade["side"])
    if side not in (-1.0, 1.0):
        raise ValueError("side must be +1 or -1")
    if not isinstance(m1.index, pd.DatetimeIndex) or m1.index.tz is None:
        raise ValueError("m1 needs a timezone-aware DatetimeIndex")

    # Last 15m boundary at/before t-30m. UTC flooring avoids DST ambiguity;
    # NY's UTC offsets are whole hours, so its 15m boundaries are identical.
    end = (t - 30 * MINUTE).tz_convert("UTC").floor("15min").tz_convert(NY)
    start = end - 15 * pd.Timedelta(minutes=15)  # 14 TRs + preceding close
    cols = ["open", "high", "low", "close"]
    x = m1.loc[(m1.index >= start) & (m1.index < t), cols].copy()
    x.index = x.index.tz_convert(NY)
    expected = pd.date_range(start, t - MINUTE, freq="min")
    if not x.index.equals(expected):
        raise ValueError("missing, duplicate, unordered or non-minute history")
    a = x.to_numpy(dtype=float)
    if not np.isfinite(a).all() or (a <= 0).any():
        raise ValueError("OHLC must be finite and positive")
    if ((x.high < x[["open", "close", "low"]].max(axis=1)).any()
            or (x.low > x[["open", "close", "high"]].min(axis=1)).any()):
        raise ValueError("invalid OHLC geometry")

    b = x.loc[x.index < end].resample(
        "15min", label="left", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    if len(b) != 15 or (b.index + pd.Timedelta(minutes=15) > end).any():
        raise ValueError("incomplete baseline")
    pc = b.close.shift(1)
    tr = pd.concat(
        [b.high - b.low, (b.high - pc).abs(), (b.low - pc).abs()], axis=1
    ).max(axis=1).iloc[1:]
    scale = float(tr.mean())  # exactly 14 TRs; SMA, not Wilder ATR
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("non-positive baseline range")
    return side, x.close.to_numpy(dtype=float), scale


def flag(trade: dict, m1: pd.DataFrame) -> bool:
    """Flag a material, efficient 15-minute move AGAINST the intended side."""
    side, close, scale = _window(trade, m1)
    p = close[-16:]  # prices at t-15m,...,t (minute-ending prices)
    signed_move = side * float(p[-1] - p[0])
    path = float(np.abs(np.diff(p)).sum())
    return bool(
        path > 0.0
        and signed_move <= -0.50 * scale
        and -signed_move >= 0.70 * path
    )
```


**two_way_chop_v1.py**

```python
"""Round 3, A2. Frozen 2026-10-26. Research flag; no trading or outcome reads."""
from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"
MINUTE = pd.Timedelta(minutes=1)


def _window(trade: dict, m1: pd.DataFrame):
    """Past-only, complete minute data; errors mean UNAVAILABLE, never 'keep'."""
    t = pd.Timestamp(trade["ts"])
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError("ts must be timezone-aware")
    t = t.tz_convert(NY)
    if t != t.tz_convert("UTC").floor("min").tz_convert(NY):
        raise ValueError("ts must be a minute boundary")
    side = float(trade["side"])
    if side not in (-1.0, 1.0):
        raise ValueError("side must be +1 or -1")
    if not isinstance(m1.index, pd.DatetimeIndex) or m1.index.tz is None:
        raise ValueError("m1 needs a timezone-aware DatetimeIndex")

    # Last 15m boundary at/before t-30m. UTC flooring avoids DST ambiguity;
    # NY's UTC offsets are whole hours, so its 15m boundaries are identical.
    end = (t - 30 * MINUTE).tz_convert("UTC").floor("15min").tz_convert(NY)
    start = end - 15 * pd.Timedelta(minutes=15)  # 14 TRs + preceding close
    cols = ["open", "high", "low", "close"]
    x = m1.loc[(m1.index >= start) & (m1.index < t), cols].copy()
    x.index = x.index.tz_convert(NY)
    expected = pd.date_range(start, t - MINUTE, freq="min")
    if not x.index.equals(expected):
        raise ValueError("missing, duplicate, unordered or non-minute history")
    a = x.to_numpy(dtype=float)
    if not np.isfinite(a).all() or (a <= 0).any():
        raise ValueError("OHLC must be finite and positive")
    if ((x.high < x[["open", "close", "low"]].max(axis=1)).any()
            or (x.low > x[["open", "close", "high"]].min(axis=1)).any()):
        raise ValueError("invalid OHLC geometry")

    b = x.loc[x.index < end].resample(
        "15min", label="left", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    if len(b) != 15 or (b.index + pd.Timedelta(minutes=15) > end).any():
        raise ValueError("incomplete baseline")
    pc = b.close.shift(1)
    tr = pd.concat(
        [b.high - b.low, (b.high - pc).abs(), (b.low - pc).abs()], axis=1
    ).max(axis=1).iloc[1:]
    scale = float(tr.mean())  # exactly 14 TRs; SMA, not Wilder ATR
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("non-positive baseline range")
    return side, x.close.to_numpy(dtype=float), scale


def flag(trade: dict, m1: pd.DataFrame) -> bool:
    """Flag active 30-minute back-and-forth movement with little net progress."""
    _, close, scale = _window(trade, m1)
    p = close[-31:]  # prices at t-30m,...,t (minute-ending prices)
    net = abs(float(p[-1] - p[0]))
    path = float(np.abs(np.diff(p)).sum())
    return bool(path >= 2.00 * scale and net <= 0.20 * path)
```


**B — `wait_for_m15_v1`: exact execution steps**

1. **Freeze the original decision.** At `t0`, evaluate `opposing_path_v1.flag()` using only minutes starting before `t0`. Save side `s`, the effective original protective stop `S0`, original actual bid/ask fill `F0`, original quantity `q0`, and the original cell's complete management configuration. Let `D0 = s*(F0−S0) > 0` and original cash-risk budget `B0 = q0*D0` in the same instrument value units. Normalize `q0=1` if the isolated trade simulator uses unit quantity. If A1 is false, execute the original policy unchanged. If inputs are unavailable, mark the opportunity unavailable; do not silently turn this into a skip win.

2. **Create one pending opportunity.** If A1 is true, do not enter at `t0`. Expiry is `t0 + 30 elapsed minutes`, inclusive for a qualifying close exactly at expiry. Do not use the 15m candle that closed exactly at `t0` as confirmation; its information was already available when the adverse path was detected. Do not reset or extend the deadline.

3. **Check cancellation first, on every subsequent minute.** Beginning with the minute starting at `t0`, cancel permanently if the original stop would be touched: bid low `<= S0` for a long; ask high `>= S0` for a short. Also cancel if mid high `>= F0 + 0.50*D0` for a long, or mid low `<= F0 − 0.50*D0` for a short. The favourable barrier uses mid prices because the current live-management replay detects its R steps on mid extremes. Cancellation applies even if price later returns, and it takes priority over a confirming close in that same minute. If both barriers occur within one minute, cancel without guessing their order. The pre-entry high/low of the original signal minute is not a subsequent excursion.

4. **Preserve entry eligibility while waiting.** Cancel on a missing minute, the existing session entry window closing, an existing news blackout beginning, the original cell's flatten deadline, or a newly available bias update that violates its original alignment rule. Apply the original profile's remaining hard risk/position limits at an attempted fill. These are the already-frozen live gates, not new learned filters. No overnight carry of a pending signal; no new signal, stop or bias-direction selection. When only mid OHLC plus one spread per minute are available, use the existing replay's `mid ± spread/2` convention for bid/ask extremes and label that approximation explicitly; it cannot reproduce intraminute spread changes.

5. **Wait for the first directional completed 15m candle.** At each 15m boundary `t1` with `t0 < t1 <= expiry`, build the complete interval `[t1−15 minutes, t1)` with exactly 15 valid minutes. Enter only when `s*(close−open) > 0`; an equal open and close does not qualify. The first candidate candle may have started before `t0`, but it must close after it. Its entire completed history is then known. Continue waiting after non-qualifying candles. Missing constituents cancel. There is no wick, pivot, FVG, MSS, EMA or minimum-body condition.

6. **Use the actual new fill and preserve the stop.** At that first qualifying close, form market fill `F1` from that minute's close and its actual spread, with the same slippage/fee convention as the immediate-entry arm. Keep `S1 = S0`; never widen or move the original stop to manufacture room. Let `D1 = s*(F1−S0)`. Enter only if `0.50*D0 <= D1 <= 1.50*D0`, price/stop orientation is valid, and the original spread/risk/exposure gates pass. Otherwise cancel the opportunity; do not wait for a second qualifying candle. Use `q1 = min(q0, B0/D1)`, rounded down to valid instrument units. This caps initial cash risk at the original budget and never increases the original quantity. A nonpositive or untradeable quantity cancels. A spread spike at confirmation cannot bypass these checks.

7. **Re-anchor the original management in new R.** If the original fixed target or first partial is `k` R, its new trigger is `F1 + s*k*D1`. Preserve the exact original `k`, partial fractions, breakeven/trailing multiples, pyramid rules and structural-management settings for that cell; invent no new target and add none to a profile that had none. All original R-based price levels now use `F1,D1`. Subsequent stop moves retain the original ratchet rule. R-based add sizing uses the new initial quantity and the existing never-risk-open-profit checks. Management begins with the minute **after** the fill minute: no target, stop or partial may use its pre-entry extremes. Hold/stall clocks start at `t1`, as for an ordinary new entry; the same day's absolute flatten time stays unchanged. Thus B is an entry-and-management policy comparison, not proof that candle confirmation alone caused any improvement.

8. **Expire without a trade.** If no qualifying entry occurs by the deadline, or any cancellation occurs, record zero P&L for that original opportunity. Keep its reason and elapsed wait in the evaluation ledger. Do not read its eventual `r`, `exit_ts`, `exit` or `mfe` to decide whether to wait, cancel or fill. Its original outcome may be joined only afterward for the paired evaluation.

9. **Compare on an equal original-risk denominator.** For the isolated paired study, calculate delayed P&L after all matching execution costs divided by `B0`. If the simulator returns `r_new` in new initial-risk units, the conversion is `r_new*q1*D1/(q0*D0)`; include all partials and adds consistently. The immediate arm is its original net P&L/B0. The skip arm is zero on flagged opportunities and the original outcome on unflagged opportunities. Include unfilled/cancelled opportunities as zeros; report both paired policy differences and delayed-fill-only net R. Use the gates in section B. A lower new risk must not inflate the reported improvement merely by changing the denominator.

10. **Replay the book separately before deployment.** The paired study keeps the original trade-opportunity ledger fixed to isolate the decision. It does not account for positions competing for the same capital or for new opportunities admitted after a skip. A full event-driven replay must use the frozen **complete candidate stream**, including candidates previously rejected as busy, with the original deterministic tie-break order. One pending opportunity reserves that original cell's slot; later candidates in that cell are rejected while it is pending, and normal position limits apply after it fills. Other cells retain the existing shared limits. Releasing a cancelled opportunity occurs when cancellation becomes known, never at the original trade's future exit. If only the executed trade rows are available, label the result a paired opportunity study, not a deployable portfolio backtest.
