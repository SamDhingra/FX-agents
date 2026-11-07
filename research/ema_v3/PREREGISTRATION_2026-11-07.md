# EMA21 family, round 3: cross without RSI, and H1-aligned: pre-registration (Nov 7, 2026, before any run)

## Why

Astra reviewed EMA21 + RSI55 (its review is in the Nov 7 chat). It recommended two standalone changes and a random-timing
control. Earlier rounds (`ema21_rsi55`, `ema21_rsi55_v2`, `ema21_rsi55_short`: 60 variants on Oct 2024 – Sep 2026)
passed nothing. Neither change below was among them.

Prior, written down now: the Nov 6 trade atlas found every playbook setup at about zero edge before costs, MACD cross
included (−0.05R on 34k trades). Rejection is the likely outcome. A clean rejection closes this family.

## Specification fixed for every configuration (including the reference)

- **Bars.**
  - 15-minute mid candles, labelled at their close.
  - EMA21 on closes; RSI(14) Wilder; ATR(14) Wilder.
  - The code is `simple_rules.bars`, unchanged.
- **Side and hours.**
  - Long only, the "day" version.
  - The signal candle closes 02:00–15:30 New York.
  - Flat at 15:50 NY.
  - Exits at the last bid before a market closure longer than 60 minutes.
- **Entry.** Buy at the ask on the next minute's open (that minute must start within 5 minutes of the candle close).
- **Exits.** The first of:
  - **EMA exit:** the first completed 15m candle closing below EMA21 → sell at the bid on the next minute's open.
  - **15:50 flatten.**
  - **Closure exit:** at the last bid before a closure.
  - **Stop:** a resting stop at entry − 3 × ATR(14, 15m) at entry, exactly as the live `ema21_rsi55` book places it.
    - It is hit when a minute's bid low reaches it.
    - The fill is the stop price, or that minute's bid open if price gapped through.
    - Minutes are checked from the entry minute up to the minute before the exit fill.
- **One trade at a time** per instrument and configuration. A signal while in a trade is ignored.
- **R** = ATR(14, 15m) at entry, frozen.
  - The 3 × ATR stop is the sizing distance, so 1 stop-out ≈ −3R.
  - The live book's journal R is in stop units; this report shows both.
- **Costs and fills.**
  - Fills are the real OANDA bid/ask, so one spread is paid per round trip.
  - "2× costs" subtracts one more spread (entry spread + exit spread) ÷ 2, in R.

## Configurations (3 instruments × 2 = 6, plus the reference)

| name | entry candle i (all on completed candles) |
|---|---|
| `ref` (not judged) | c[i−1] ≤ EMA21[i−1], c[i] > EMA21[i], RSI(14)[i] > 55: the original rule, with the stop above |
| **`A_norsi`** | c[i−1] ≤ EMA21[i−1] and c[i] > EMA21[i]; no RSI condition |
| **`B_h1`** | the `ref` condition, and the last COMPLETED 1-hour mid candle at the signal candle's close closed above its own EMA21 (1h EMA21 on 1h closes) |

Instruments are XAUUSD, NDQ and US30, each judged separately. There are no other lengths, levels or combinations.

## Random-timing control (causal)

- **Pool.** For every trade, the pool is every candle in the same period half, at the same NY hour of the signal
  candle's close, inside the entry window, closing above its EMA21 (the long state), with a tradable next minute.
- **Simulation.** Each pool candle is simulated as an entry with the same exits (EMA exit, stop, 15:50, closures).
  - control_i = the mean R of 20 random draws from that pool, with seed 7.
  - d_i = R_i − control_i.

## Gates per configuration (all required)

1. at least 100 trades;
2. the 95% range of mean R (5-day blocks of weekdays, zero-trade days included) above 0;
3. mean R at 2× costs above 0;
4. mean R above 0 in both halves of the period;
5. the 95% range (same blocks) of the mean d vs random timing above 0;
6. incremental daily result vs `ref` above 0: the mean over all weekdays of (that day's total R − `ref`'s total R
   that day). This is a point estimate.

**Multiplicity.** Gate 2 uses the ordinary 95% range. Each later stage is the guard against the six-way search. A
99.2% range (Bonferroni for 6) is shown as information.

## Stages

| stage | data | split | who goes |
|---|---|---|---|
| dev | `dev_m1`, 2024-10-01 → 2026-09-30, **already seen**: screening only | 2025-10-01 | all 6 |
| holdout | `holdout_m1`, 2021-01-01 → 2024-09-30, never used for this family | 2022-11-16 | only configurations passing dev |
| vault | `old_m1`, 2016–2020, used once for this family | 2018-07-01 | ONE nominee: of the configurations passing holdout, the one with the highest holdout lower bound of mean R |

- A vault failure closes the family. The runner-up is not sent.
- Each stage refuses to run unless the previous stage's summary shows a pass.

## What follows

- **Nothing passes dev or holdout:** EMA21 research stops. The `ema21_rsi55` paper book continues only as a record.
- **The nominee passes the vault:** it runs as a separate paper book beside `ema21_rsi55`, frozen, and is reviewed
  after 100 forward trades. It is not promoted to the live account on this evidence alone.

## Information (never a pass)

- `ref` without the stop, which reproduces the earlier v2 "day" long numbers as a code check;
- the exit-reason mix and the stop-hit share;
- trades per day.
