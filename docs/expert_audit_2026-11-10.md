# FX-agents: outside audit (Nov 10, 2026)

Tags: **[E]** evidence from a file I read (cited), **[R]** reasoning, **[S]** speculation.
Not read: `index.html`, the strategy classes, the live branch, any `.env`. No code was run.

## The single most important finding

**The search space has a gross edge of zero, and the pass gates need an edge that this kind of trading almost never has.**

- [E] In the atlas, doubling the cost doubles the loss: indices −0.09R → −0.19R, gold −0.16R → −0.32R
  (`atlas_history/report.md`, section 1). So one spread costs about 0.09R (indices) or 0.16R (gold), and what is left
  before costs is 0.00R. 29 setups × 1.07M trades are random entries that pay the spread.
- [R] Per-trade spread of results is about 1.2R (C10: 251 trades, 95% half-width 0.148R). To clear the 95% gate with
  80% power you need about 11.3 ÷ edge² trades: 4,500 trades for +0.05R, 1,130 for +0.10R, 180 for +0.25R.
  In Sharpe terms, 5.75 years of seen data only passes reliably at an annual Sharpe near 1.2, and then again on the
  vault. Public price patterns at retail CFD costs do not produce that.
- [R] So the outcome so far is what the design guarantees: correct rejections of nothing-edges, plus guaranteed
  rejection of any small real one. More setups, filters or exits cannot change this. My honest prior that any
  M1–H1 pattern idea passes both stages is under 2%.

## 1. Diagnosis

1. **Cost relative to horizon is the binding constraint.** [E] Spread ÷ risk is 2–6% on index cells and 8–17% on gold
   3m cells (`playbook_test/report.md`). At a 3–15 minute horizon the stop is a few spreads wide, so a setup must
   predict direction by 5–10% of its risk just to reach zero. [R] Nothing in a candle shape carries that much.
2. **The setups are worse than random, which is itself informative.** [E] Random same-day entries: −0.044R; the
   setups: −0.090R; the opposite side is no better (`entry_edge` outcome). [R] Both sides losing more than random
   means signals fire when trading is expensive (wide spread, fast tape), not that direction is wrong. Inverting
   them will not work either.
3. **Filters and exits are mathematically too small.** [E] Every filter or exit tested moved results by ±0.01–0.03R
   (chop, m15_wait, floor, trend_protect, gold_trail) against a −0.07 to −0.09R base. [R] An exit rule on a
   zero-edge entry only reshapes the distribution; the mean stays at minus cost. Five tests have now confirmed it.
4. **The one pass is economically small.** [E] C10: +0.258R on seen (251 trades), +0.082R on the vault, not
   significant (`bt_gpt_c10…` reports). [R] At about 44 trades a year and a shrunk edge of +0.10R, that is 4–5R a
   year: about 2% a year at 0.5% risk. Confirming +0.10R forward needs about 1,130 trades, roughly 25 years.
5. **The process is honest but spends effort on low-value tests.** [R] 20 registrations and about 15 `bt_*` plug-in
   tests were each run without asking first "if this is as good as it plausibly could be, would it pass, and would
   it matter?" Most would have been declined on that question alone.
6. **The vault is not a like-for-like judge.** [E] Spread was 5% of the stop in 2016–2020 against 2% in 2021–2026
   (`trend_hold` outcome, part 2). [R] A vault failure mixes "no edge" with "older, wider spreads".

## 2. Edge candidates (ranked by my prior of a full pass)

None of these is likely. Combined, I put the chance that at least one passes seen **and** vault at about 15–20%.

**1. C10 replicated on instruments it has never seen (US2000 first, US30 second). Prior: 20%.**
- Why it could exist [E/R]: hedging demand. Dealers short gamma and leveraged ETFs must trade in the direction of
  the day's move into the close (Baltussen et al. 2021, cited in `imom`). They pay because their hedge is forced.
- Why it differs: it is the only family here with a pass on record, and this adds no parameters: frozen code on a
  fresh sample. [E] `imom` (a different rule, first move → last half-hour) failed on US30, which lowers the prior.
- Data: OANDA 1-minute bid/ask for US2000_USD and US30_USD, 2016–2026. US30 is in hand; US2000 history must be
  pulled with the existing exporter.
- Test: see the draft registration at the end.

**2. Overnight reversal at the European open after US sell-off days. Prior: 12%.**
- Why [S]: Boyarchenko, Larsen & Whelan ("The Overnight Drift", NY Fed) find the overnight gain in US index
  futures concentrated around 02:00–03:00 New York, larger after days that closed with heavy selling. Dealers who
  absorbed the selling at the close shed inventory when Europe arrives; sellers at the close paid for immediacy.
  I am quoting the mechanism from memory, not the effect sizes.
- Differs: inventory flow on the daily clock, no chart input, no financing (in after 17:00, out before it).
- Data: in hand (NDQ, US30 1-minute bid/ask around the clock).
- Test: on days when the 14:00→16:00 return is in the lowest fifth of the trailing 250 days, long 01:30→03:30 NY at
  real bid/ask. About 290 trades on seen. Controls: the same window on all other days, and random 2-hour overnight
  windows on the same nights. Gates as usual, in basis points. [R] Needs about +3 bps net to pass; the overnight
  spread alone is 1–1.5 bps.

**3. Gold Asian-hours drift. Prior: 10%.**
- Why [S]: physical buying is concentrated in Asian hours and Western hedging and fix-related selling in London/NY
  hours; a long-documented intraday seasonality. The other side is hedgers who trade on their own clock.
- Differs: a session premium rather than a breakout. [E] It overlaps the hours of the `gold_breakout` book, whose
  result is concentrated in the recent gold trend (`gold_add05` outcome), so trend must be controlled for.
- Data: in hand.
- Test: long 18:05→03:00 NY daily, about 1,450 trades. Control: equal-length long windows at other hours of the same
  days (this removes the 2024–2026 bull run). Pass requires the difference, not the raw return, to clear the gates.

**4. Turn of the month on indices. Prior: 8%, and it does not fit the gates.**
- Why [S]: salary, pension and fund flows arrive at month-end; the last day plus the first three have historically
  carried most of the equity premium.
- Data: in hand; financing must be charged (4 nights ≈ 7 bps at the 5% rate used in `trend_hold`).
- [R] Only 69 windows exist on seen data. It cannot reach 100 independent trades without merging seen and vault,
  which the rules forbid. I list it to show the limit, not to recommend it.

**5. Diversified daily trend across 20+ OANDA CFDs. Prior it is real: about 60%. Prior it passes your gates: 5%.**
- Why [R]: the best-documented premium available to a price-only trader (slow reaction, hedgers paying for risk
  transfer), supported by decades of out-of-sample history rather than by your 5 years.
- Data: daily bars for about 20 more OANDA instruments (FX majors, bonds, commodities, indices).
- [R] Expected Sharpe after CFD financing is 0.2–0.4. That is a t-statistic near 1 in 5.75 years. The gates will
  reject it whether or not it is real. This is the clearest case of the gates deciding the answer.

**What I would do instead, said plainly:** [R] a low-cost index fund in a TFSA or RRSP earns the equity premium with
no spread, no 2.5% financing mark-up and no tax drag. Every candidate above must beat that, after tax, to be worth
real money. Confirm the tax treatment of CFD gains with an accountant; I have not checked it.

## 3. Process improvements

1. **A two-line pre-check on every registration, before code is written.** [R] (a) Trades available × plausible
   edge ÷ 1.2R gives the expected t-statistic; decline anything under 2.8. (b) Edge × trades per year gives R per
   year; decline anything under about 10R. Both lines go in the registration. This alone would have declined most
   of the filter and exit tests.
2. **A rule for what cannot matter.** [R] No filter or exit test on a base whose average is below zero unless its
   best case exceeds the base's deficit. [E] `m15_wait` passed at +0.009R on a −0.09R book.
3. **One shared baseline, computed once.** [R] Random-timing results per instrument × hour × stop size × hold, stored
   and versioned. [E] Each test currently builds its own control (`entry_edge`, `ema_v3`, `supertrend`, bt harness).
4. **A project-wide error ledger.** [R] One file listing every test, its family, the data it touched and its p-value.
   About 35 tests at the 95% level means one or two false passes on seen are expected; C10 should be read with that
   in mind. Tighten the seen gate to 99% for new families, or count vault uses explicitly.
5. **Log every vault opening.** [E] C10 v1 ran on the vault at 23:38, then v2 ran on seen at 23:51:06 and on the
   vault at 23:51:56 the same night (report headers). That is two openings for one family, with v2 written after
   v1's vault result existed.
6. **Judge the vault at matched costs as well.** [R] Pre-register a second vault figure with spread scaled to the seen
   period's spread ÷ stop. It separates "no edge" from "old spreads".
7. **A second track for known premia.** [R] For ideas like candidate 5, your data cannot supply the evidence; the
   literature does. The test there is implementation and cost: does the net result match the published one within
   its range at 2× costs? Decide now whether you accept that track. If not, close that class of idea for good.

## 4. Trading and risk now

- **Live account: nothing new.** [R] No book has passed both stages. If Sam wants C10 live, the size should be
  0.1–0.25%, with a written stop rule (for example: end at −10R, or at 100 forward trades below zero).
- **Undo the Nov 9 risk increases.** [E] `config.yaml:220` raised C10 from 0.25% to 0.5% while its own comment says
  the vault was not significant; `config.yaml:227–236` put gold breakout and H1 trend on the account at 0.5%, with
  the comment that the breakout failed its 2021–2024 holdout and H1 trend was not significant (+0.07R, 103 trades).
  [R] These are failed or unproven ideas given full size. It is practice money, but it sets the habit the live
  account will inherit, and it breaks "a failure closes the idea".
- **Stop the hourly pick.** [E] It ranks strategies on a 10-day lookback (`config.yaml:204`) and selects at a score
  of 0.55 (`config.yaml:187`, `trading.py:220`). [R] With a true mean near −0.07R and a 10-day standard error near
  0.25R, the hourly "best" is the luckiest loser. Expected result: minus cost per trade.
- **Stop the four playbook paper books.** [E] 1.07M simulated trades, the 528-trade walk-forward and the
  hours/bias test already answer what they are measuring.
- **Keep as data collection:** C10, gold breakout and H1 trend on paper at a fixed small risk; and a
  fill-quality log (spread and slippage at entry, stop and target against the simulator's assumption). [R] That log
  is the one live dataset that improves every future test.
- **Turn off Jev and the model reviewers.** [E] Jev has zero weight but is still called every hour
  (`trading.py:203`); the Claude review gate still runs on books I recommend stopping (`config.yaml:280–283`).
- **Drawdown rules:** the 2% daily and 6% peak kill switches are fine. [R] Add a per-book forward stop in R, set at
  registration.

## 5. Dashboard

- **Add one view: the evidence ledger.** [R] One row per book: registered expected R per trade, forward trades,
  forward average R with its 95% range, a chart of cumulative R against two cones (registered edge, zero edge minus
  cost), spread paid to date in R, and "trades still needed to tell the two apart". It answers the only question
  that should move money: is this book distinguishable from zero yet?
- **Remove as noise:** [E] by-hour, weekday, session, holding-time and bias tables, streaks, the giveback list and
  `big_payoff`, which flags setups on as few as 5 trades (`analysis.py:198–210, 212–229, 262–268`). [R] The atlas
  showed hour and bias carry no signal at a million trades; on 30 days of live trades these tables can only
  manufacture stories. The exit question behind the giveback list has been closed five times. Also the setup map
  and the Jev scorecards.

## 6. Fixes

1. **Stops trigger on an approximated bid.** [E] `research.py:219–223` uses mid low minus half the minute's *closing*
   spread, and fills at exactly the stop price. The export has real bid/ask highs and lows, and
   `playbook_test.py:69–71` throws them away. [R] Stop-outs during spread spikes are missed and slippage is zero:
   optimistic. It does not rescue any failed test, but it flatters C10 and the gold books.
2. **Targets differ between replay and live.** [E] `research.py:262–268` fills targets at the minute's close when the
   mid touches; live rests a limit filled at the level when the bid touches (`oanda.py:684–687`,
   `config.yaml:26`). The docstring at `research.py:163` ("OANDA ignores limit prices") is out of date. [R] Roughly
   unbiased on average, but "engine reproduces 100%" does not mean "matches live".
3. **News blackout differs by period.** [E] `research.py:322–340`: FOMC dates exist for 2024–2026 only, and NFP is
   "first Friday". Replays of 2016–2023 have no FOMC blackout, so the two halves and the vault run under different
   rules.
4. **`cost_r` in research is not what Risk enforces.** [E] `research.py:498` uses the median spread
   (`research.py:415`); live uses the quote at entry (`trading.py:498–499`). The 8% cost cap was validated on the
   first and is enforced on the second (`config.yaml:130`).
5. **Stale picks can survive an hour.** [E] `trading.py:172` marks the hour done, then `trading.py:179–180` returns
   without clearing `state.selections[sym]` when no live strategy has stats; `trading.py:247` reads it with no hour
   check. [R] Likely bug; confirm with a test.
6. **Zero-weight Jev still shapes the ranking.** [E] `trading.py:206` ranks only the strategies in Jev's reply.
   [R] Skip the call when the weight is 0.
7. **Selection threshold does not gate.** [E] `trading.py:365`: +0.10R on 20 trades gives a score above 0.55. [R] See
   section 4.
8. **Small:** [E] the playbook report prints a literal `{len(cells)}` (`playbook_test/report.md`, Step 1 line);
   `c10_trader.py` docstring still says risk 0.001 and 0.25%.

---

# Draft: C10 on unseen instruments (US2000, US30): pre-registration (draft, Nov 10, 2026, before any run)

## Why

C10 v2 is the only rule in the project that passed its seen-period gates (NDQ, 251 trades, +0.258R) and it was
positive but not significant on 2016–2020 (+0.082R). It has been tested on NDQ only. Its claimed mechanism, hedging
flows that continue the day's move into the afternoon, is not specific to NDQ. US2000 has never been run through
any test in this project; US30 has not been run in this rule. A frozen rule on fresh instruments is the cheapest
test we have of whether C10 is a flow effect or one lucky draw among about 35 tests.

## Rule

`gpt_c10_afternoon_continuation_v2`, code 8d23c814cc28, **unchanged**: no parameter, threshold, hour or exit is
edited. Real 1-minute bid/ask, the plug-in's own cost skip rule and gates.

## Data

- US2000_USD (primary) and US30_USD (supporting), OANDA 1-minute bid/ask.
- Seen: 2021-01-01 → 2026-09-30. Halves split at the elapsed midpoint.
- If US2000 history is missing more than 5% of 09:30–15:45 minutes in any year, that year is dropped and reported.

## Before the run (written here, not changed afterwards)

- Expected trades: about 250 per instrument. Result spread: about 1.2R per trade.
- This test detects a true +0.21R with 80% power. A true +0.10R passes about one time in four.
- If real at +0.10R, it adds about 4–5R a year per instrument, less on days shared with NDQ.

## Gates (all required, US2000 decides)

1. at least 100 trades;
2. the 95% range of average R above 0 (5-trading-day blocks);
3. average R above 0 at 2× costs;
4. both halves above 0;
5. beats the exact coin flip and random timing (same side, time of day, stop % and hold, other days), with the
   95% range of the difference above 0.

Information only, never a pass: US30; the result on days when NDQ's C10 did not trade; by year; long and short.

## Outcomes

- **US2000 passes** → judged once on 2016–2020 (`vault`), also reported at seen-period spread ÷ stop. A vault pass
  opens a US2000 paper book at 0.1%; the index group still allows one position per direction.
- **US2000 fails, average R above 0** → no change. C10 stays a paper record; the account's C10 risk returns to 0.25%.
- **US2000 average R at or below 0** → C10 is treated as a chance result: the account book stops, the paper book
  runs to 100 forward trades and is then judged against zero.
- US30 cannot rescue a US2000 failure, and no variant is tried on these instruments afterwards.
