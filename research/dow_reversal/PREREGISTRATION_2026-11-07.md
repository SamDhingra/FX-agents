# US30 one-stock reversal: pre-registration (Nov 7, 2026, before any data is fetched or read)

## Source and scope

From "Three instrument-specific strategies for FX-Agents" (Astra, Nov 7 2026), strategy 3. Only US30 is run now:

- **US30** can be built from free data: Alpaca's free plan has US stock minute bars since 2016.
- **Gold**, the near-contract repricing idea, is not run. It needs second-stamped quotes for individual COMEX expiries.
- **NDQ**, the earnings handoff idea, is not run. It needs point-in-time earnings receipt times and index weights, and
  it would have too few events for 100 trades.

**Hypothesis.** When one stock's dollar move pulls the price-weighted Dow, then stalls while the other members turn
against it, US30 tends to give the move back.

**The control.** The same breadth turn on swings where no stock dominates. If that does as well, concentration adds
nothing.

## Data

- **Stocks.** Alpaca historical 1-minute bars from the SIP feed with `adjustment=raw` (as-traded dollars: the Dow is
  price-weighted).
  - Each ticker is queried only over its own membership period, with `asof` set to that period's start, so renamed
    tickers resolve point-in-time.
  - The fetcher reads `ALPACA_KEY_ID` / `ALPACA_SECRET_KEY` from `.env`. They are never logged or written anywhere else.
- **Members.** A frozen list, effective before the open on each date. The source is the Wikipedia historical
  components list, plus S&P DJI's Jun 23 2026 release:
  - 2016-01-01: MMM AXP AAPL BA CAT CVX CSCO KO DD XOM GE GS HD INTC IBM JNJ JPM MCD MRK MSFT NKE PFE PG TRV UNH UTX VZ V
    WMT DIS
  - 2017-09-01: +DWDP −DD
  - 2018-06-26: +WBA −GE
  - 2019-04-02: +DOW −DWDP
  - 2020-04-03: +RTX −UTX (the UTX/Raytheon merger; the index switched on Apr 6)
  - 2020-08-31: +AMGN +HON +CRM −XOM −PFE −RTX
  - 2024-02-26: +AMZN −WBA
  - 2024-11-08: +NVDA +SHW −INTC −DOW
  - 2026-06-29: +GOOGL −VZ
- **Days skipped.** Every change date above, and 2020-04-06.
- **US30.** The OANDA bid/ask 1-minute exports: `holdout_m1` + `dev_m1` for 2021 → Sep 2026, `old_m1_idx` for
  2016–2020.

### Deviations from the source, stated now

1. **Stock prices are minute-bar closes, not quotes at most 2 seconds old.** "Price at T" = the close of the bar
   starting T−1 min. If that bar is missing, the latest bar starting in [T−3, T−1] min is used. If there is none, that
   member is missing.
2. **Incomplete baskets are skipped.** A scan time with any of the 30 members missing at any of its three endpoints is
   skipped and counted as a data gap.
3. **Split days are not skipped.** Raw prices within one session are consistent, so the concentration ratio is not
   affected. The divisor is not needed for the ratio.
4. **Costs.** OANDA charges no commission. The estimated round-trip cost is the full broker spread at decision × 1.1.
   Fills use the real bid/ask, with no extra slippage.

## Rule (version 1, the source's thresholds, unchanged)

- **Scans.** Every 5 minutes, t = 10:00 … 11:15 and 13:45 … 14:50 New York.
- **Formation, t−20 → t−5.**
  - D_i = each member's dollar change.
  - L = the unique member with the largest |D_i|. A tie means skip.
  - s = sign(ΣD_i).
  - Requirements:
    - L moved in direction s;
    - |D_L| ≥ 0.35 × Σ|D_i|;
    - US30's mid moved in direction s by at least 1 × A₅, where A₅ = the simple average true range of the 14 complete
      5-minute mid bars ending at or before t−5.
- **Pause, t−5 → t.** With F_i = each member's change:
  - |F_L| ≤ 0.10 × |D_L|;
  - at least 18 of the other 29 have F_i against s;
  - the sum of the other 29's F_i is against s.
- **Retention.** US30's mid move from t−20 to t must be at least 0.70 × its move from t−20 to t−5, in direction s.
- **Trade.** The side is −s (fade the narrow move). Only the first qualifying scan per day counts. A qualifying signal
  that is refused at execution still uses up that day.
- **Execution and risk** (the source's common rule).
  - A = the simple average true range of the 14 complete 5-minute mid bars ending at or before t. The 15 bars must be
    consecutive.
  - Stop = mid(t) − side × 1.5A, frozen.
  - Entry is at the open of the minute starting at t: ask for a buy, bid for a sell.
  - The trade is refused if:
    - |entry − mid(t)| > 0.15A;
    - the entry is on the wrong side of the stop;
    - the estimated cost is above 10% of |entry − stop|.
- **Exit.**
  - **Stop:** checked from the entry minute on the executable side. The fill is the stop, or the minute's open if price
    gapped through it.
  - **Time:** otherwise out at the open of the minute starting at t + 20, on the executable side.
  - No partials, no trailing, no adds.
- **Results.** R = side × (exit − entry) ÷ |entry − stop|, and basis points of entry. "2× costs" subtracts one more
  (entry spread + exit spread) ÷ 2.

## Control (primary): breadth turn without concentration

- **Rule.** The same scans, s, ATR gate, retention, execution and exits. The difference:
  - the largest mover's share is ≤ 0.20 of Σ|D_i|;
  - "the other 29" is the 29 members other than the largest mover, which must not pause;
  - first qualifying scan per day.
- **Matching.** Each rule trade is matched to the control trade with the nearest |US30 formation move| ÷ A₅ in the same
  stratum. Ties go to the nearest date. Controls may be reused. The stratum is:
  - the same period half;
  - the same 30-minute clock bucket of t;
  - the same side;
  - the same tercile of prior-20-session realized volatility. Volatility is the standard deviation of US30's daily
    15:59 → 15:59 mid returns, ending the previous day. Tercile cut points come from the stage's own days.
- **Paired difference.** d = R(rule) − R(matched control).

## Gates (all required)

1. **Counts first.** At least 100 filled trades on at least 100 distinct days. Below that, the result is
   **inconclusive**, the report shows counts only, and no threshold is changed.
2. Matched-control coverage at least 90% of filled trades.
3. The 95% range of mean R above 0. Resampling uses 5-session blocks of trading days, keeping zero-event days.
4. Mean R above 0 in both halves.
5. Mean R above 0 at 2× costs.
6. The 95% range (same blocks) of the mean paired difference d above 0.

**Multiplicity.** Only one of the source's three candidates is run, so the ordinary 95% range (one-sided 97.5%) is
used. The source proposed one-sided 98.33% for three candidates. It is shown as information.

## Stages

| stage | data | halves split | rule |
|---|---|---|---|
| seen | 2021-01-01 → 2026-09-30 | 2023-11-17 | all gates |
| vault | 2016-01-01 → 2020-12-31, once | 2018-07-01 | runs only after a seen pass |

- A failure at either stage closes this idea. No threshold is changed and it is not re-run in another form.
- A vault pass leads to a separate US30 paper book with a live Dow-constituent feed, reviewed after 100 forward trades.

## Information (never a pass)

- data coverage per member and per year;
- refusals by reason;
- the one-sided 98.33% bound;
- concentration recomputed with percentage changes;
- after entry: did the leader resume (moved in direction s during the trade), or did the other 29 continue against s;
- results by year, side and exit reason;
- best five trades' share of the total.
