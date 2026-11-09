# Can Jev read the next hour from candles? Historical replay: pre-registration (Nov 9, 2026, before any Jev call)

## Why

Jev carries 60% of the hourly pick's score (`jev.weight`) and gates its signals, but no test has shown it forecasts
anything. The Oct 7 Jev check covered 23 trades, with no relationship found. Astra (Nov 9) proposed a six-month
forward test. Sam proposed replaying history to Jev instead, one moment at a time, using only data before each moment.

The risk in a replay is memory: Jev is a language model and may know the actual history. Two safeguards:
1. **Every packet is anonymised.** There are no dates, no price levels and no instrument name. Candles are expressed
   relative to the decision price, in units of the recent hourly range, so a specific day can't be recognised.
2. **Only 2026 data is used,** most of which is likely after Jev's training data.

## Data and decisions

- **Data.** `data/export/dev_m1` (OANDA 1-minute bid/ask, Oct 2024 → Sep 2026) for XAUUSD, NDQ and US30. Mid prices.
  15-minute and 1-hour candles are indexed by their close.
- **Decisions.** Every NY weekday from 2026-01-02 to 2026-09-30, at 02:00, 03:00 … 14:00 New York (13 a day), per
  instrument. A decision t is used only if all of these hold:
  - the 16 most recent 15-minute candles closed at or before t, are consecutive, and the last closes exactly at t;
  - the 16 most recent hourly candles closed at or before t, the last two are adjacent, and the last closed within
    45 minutes of t;
  - A = the simple mean of the last 14 hourly true ranges is finite and positive;
  - the next four 15-minute candles after t are consecutive (needed for grading only, never shown).
- **Label (Astra's T60, unchanged).**
  - P = the 15-minute mid close at t.
  - UP if at least 3 of the next 4 15-minute closes are strictly above P AND the 4th close ≥ P + A/2.
  - DOWN is the mirror. Everything else is NEITHER.

## What Jev sees (one call per decision; nothing after t)

- **Candles.** The 16 latest 15-minute candles and the 4 latest hourly candles. Each candle is given as minutes
  before the decision, then (open, high, low, close − P) ÷ A, rounded to 3 decimals.
- **Time.** The weekday and the New York clock time.
- **Description.** "a liquid CFD".
- **Never shown:** symbol, date, absolute prices, any chart-state verdict, any trade.

**Two typed yes/no questions (Noul), one call.** Both questions carry the same label text:
- `event`: P(UP or DOWN);
- `up_if_event`: P(UP | UP or DOWN).

From these: p_up = e·u, p_down = e·(1−u), p_neither = 1−e.

- **Coverage.** A missing, failed or unreadable answer means no Jev forecast for that decision, and it is counted.
  The heuristic fallback is never used as Jev.
- **Records kept.** Every answer is cached with the model name, so a stopped run resumes without asking again.

**Mirror check (information only).** The same packet is also sent upside down: every price is sign-flipped, highs
and lows swap. A reader of patterns should swap its up and down answers. This is reported as a consistency measure.

## Benchmarks (deployable: each decision date uses only the 252 sessions before it)

- **Hour-only.** Instrument × NY hour rates of UP / DOWN / NEITHER, with one pseudo-count per outcome.
- **Momentum-only.** Within that parent, by the sign of the previous hour's change (up / down / flat), shrunk to the
  parent with 20 pseudo-counts: (counts + 20 × parent) ÷ (n + 20).
- **Measured (the primary benchmark).**
  - Within the parent, by Astra's chart state × the previous hour's sign, with the same shrinkage.
  - Chart state is: up if the newer hourly candle has a higher high and a higher low and both latest 15-minute closes
    are above that hour's midpoint; down is the mirror; otherwise mixed.
- **Labels used.** Only labels already complete before the decision date. The 2024-10 → 2025-12 data supplies the
  first year.

## Candidate and gates

- **Candidate.** The equal-weight average of the measured benchmark's and Jev's probability vectors. Where Jev has
  no answer, the candidate equals the benchmark.
- **Score.** The multiclass Brier loss Σ_k (p_k − 1[outcome = k])² per decision.
- **Comparison.** d = Brier(measured) − Brier(candidate), so positive is better.

**PASS needs all of these:**
1. real, readable Jev answers on ≥ 90% of eligible decisions;
2. the 95% range of the mean d above 0, resampling circular 5-weekday blocks with all instruments of a date kept
   together;
3. mean d above 0 in both halves (split 2026-05-15);
4. the candidate's mean Brier below the momentum-only benchmark's.

**Information only:**
- Jev alone, every benchmark alone;
- calibration by probability band;
- per instrument;
- the directional hit rate of Jev's more likely side, against following the previous hour;
- the mirror consistency.

## What follows

- **PASS.** Jev shows forecast skill on clean candles. Next is a separately registered trading test, Astra's step 4
  (Jev-gated trend pullback against matched controls), before Jev's role in trading changes.
- **FAIL.** Jev adds nothing over a simple statistical forecast of the next hour. That is evidence for removing or
  reducing Jev's weight in the hourly pick (a decision for Sam, not automatic). The question and the gates are not
  re-run with a different prompt on these data. A new prompt version is a new registration, run on decisions not yet
  used.
