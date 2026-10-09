# FX-Agents research brief for Astra — October 2026

**Purpose:** find a trading edge that survives a test on data nobody has looked at, then hand over frozen,
runnable rules. Intraday and longer-horizon (multi-day) strategies are both in scope.
**Repository:** github.com/SamDhingra/FX-agents (branch `main`; published test results on branch `results`).
**Prepared:** 9 October 2026, from the project's own test reports.

---

## 1. The short version

Every strategy family tested so far has failed once it was checked on data it was not chosen from. The bot's
plumbing (execution, journals, dashboard, risk limits) works; what is missing is an edge. We are not looking
for a better-looking backtest. We are looking for a rule set that is positive after realistic costs on a
period that neither you nor we have seen, scored by code you freeze before that period is opened.

## 2. Account, instruments and constraints

| Item | Value |
|---|---|
| Broker | OANDA v20, practice account (CFDs and spot FX), about $70,000 |
| Traded today | XAUUSD (`XAU_USD`), NDQ (`NAS100_USD`), US30 (`US30_USD`) |
| Watched, can trade | EURUSD, GBPUSD, AUDUSD; any other OANDA instrument the account offers can be added |
| Intraday bot rules | New York time; entries in configured windows; everything flat by 15:50 NY; constant fractional risk |
| Risk per trade | starts at 0.10% of equity live; up to 0.25% after proof |
| Costs assumed so far | full spread XAUUSD 0.40, NDQ 1.50, US30 2.50 price points, plus slippage; no commission on OANDA CFDs |
| Longer horizon | allowed as a **separate** mandate: positions may be held overnight/for days, but OANDA overnight financing, weekend gaps and margin must be modelled |

## 3. What has already been tested — and failed

All numbers are average R per trade after costs (R = initial risk). "Unseen" means a period the rules were not
designed or selected on.

| What | Where it was designed / picked | Result on unseen data |
|---|---|---|
| Weekly "playbook": pick the best cells (setup × instrument × timeframe × exit) from the trailing 60 trade days, trade them next week | ICT, SMC, DTFX, VWAP, trend-breakout, RSI-pullback setups; 10,590 cells, 1.6 M simulated trades, Oct 2025–Oct 2026 | 1,989 trades, **−0.017R**, 95% day-block range −0.049 to +0.014, 22 of 49 weeks positive |
| Best individual cells from that year (e.g. gold 3m DTFX wick-fib with pullback-validated swings, gold 15m iFVG, gold 15m RSI pullback; +0.16 to +0.28R) | Oct 2025–Oct 2026 | Oct 2024–Oct 2025: **−0.13, −0.07, −0.12R** (std exit); all 95% ranges include or sit below 0 |
| Your 15 intraday strategies (ASTRA-INTRADAY-15-v0.2.0-simple), run unchanged with your own code on OANDA mid data | Vendor data 26 Mar–25 Sep 2026 | Oct 2024–Mar 2026: **nothing passes**. U-S2 −0.12R (103 trades), G-S2 +0.00R (170), N-S2 +0.05R (141, −0.02 at 2× costs), N-S1 −0.19R (71) |
| Same 15, same dates as your vendor sample but on OANDA data | — | NDQ leads vanish (N-S2 −0.08R, N-S1 −0.03R); gold/US30 EMA stay mildly positive (+0.12 / +0.10R, n < 100) |
| Your earlier 3 strategies (ORB, gap-fail, H1 volatility trend) | Oct 2025–Oct 2026 | ORB and gap-fail negative; **gold H1 trend +0.07R over 103 trades** on the earlier year — break-even at 2× costs; now running as a paper shadow book |
| Gold 15m 20/50/200 EMA trend (your G-H2) | Mar–Sep 2026 | +0.12R over 114 trades, 95% −0.06 to +0.33, +0.02R at 2× costs, fading over time |
| Exit styles (1R target + runner, scalp, 2R trend, fixed TP) | all signals | Exits don't create an edge: across all signals every exit style is negative on average; pyramid adds lose ≈0.04R per added trade |

Lessons we want you to build on, not re-learn:
- **Selection is the enemy.** With thousands of cells, hundreds look good by luck; the best ones failed on the
  earlier year every time.
- **Data source matters.** Your vendor sample had 99.99% of bars opening exactly at the prior close (smoothed
  construction); several leads disappeared on OANDA data.
- **Costs dominate short timeframes.** On 1–5 minute CFD trades the spread is a large share of each stop.
- **Intraday gold trend-following** is the one idea that has come out slightly positive twice (+0.07R, +0.12R),
  but never significantly. Treat it as a hypothesis, not a finding.

Detailed reports (all on branch `results`, folder `year_test/`): `365d_p2` (playbook, all cells),
`astra15_unseen`, `astra15_overlap`, `astra_cfd_365d`, `astra_cfd_730d_to_2025-10-07`. The audit you wrote is at
`docs/astra_audit_2026-10-08.md` on `main`.

## 4. The data you get — and the data you don't

Sam will upload OANDA exports to the project (gzipped CSV, one file per instrument):

| Set | Granularity | Window | Purpose |
|---|---|---|---|
| `dev_m1` | 1-minute **bid and ask** candles | 2024-10-01 → 2026-09-30 | intraday development |
| `dev_d` | daily bid/ask candles (17:00 NY close), wider instrument list | 2016-01-01 → 2026-09-30 | multi-day development |

Columns: `time` (UTC candle **open** time), `bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume`
(volume = OANDA tick count, not traded contracts). Only complete candles. A `manifest.json` gives row counts and
sha256 per file. Real bid/ask means you can model spread per minute instead of assuming it: a long fills at the
ask, its stop triggers on the bid.

**Holdout — never shared, never looked at by anyone:**
- intraday: OANDA 1-minute bid/ask, **2021-01-01 → 2024-09-30**
- multi-day: OANDA daily bid/ask, **2008-01-01 → 2015-12-31**
- plus the forward period: everything after the date you freeze a strategy, traded on paper.

Your frozen code will be run on the holdout on our server, unchanged. You will get the scores back, not the data.

## 5. What we need back (deliverable contract)

1. **At most 5 candidate strategies per submission.** For each: hypothesis (why the edge should exist — a
   behavioural, structural or risk-premium reason), exact rules, parameters, instruments, timeframe, sessions,
   holding period, stop/exit/sizing, and what would falsify it.
2. **A trial ledger:** every variant you tried on development data, including losers, so we can judge how much
   selection went into the winners.
3. **One self-contained Python package**, Python 3.11+, pandas/numpy only (no network):
   `python backtest.py --data-dir DIR --out-dir OUT [--start YYYY-MM-DD --end YYYY-MM-DD]`
   - reads files named `<SYMBOL>_M1.csv.gz` / `<SYMBOL>_D.csv.gz` in the format above;
   - signals use only completed bars; fills at the next tradable price on the correct side (ask to buy, bid to
     sell), stop/target triggers on the exit side, stop wins when stop and target are inside the same bar;
   - multi-day: charges OANDA financing (state the rate assumption per instrument) and handles weekend gaps;
   - writes `OUT/trades.csv` (one row per trade: strategy id, symbol, entry/exit time and price, side, R, cost in R)
     and `OUT/summary.csv` (per strategy: trades, win rate, avg R, total R, max drawdown in R, avg R at 2× costs,
     and a 95% interval of avg R from a **day-block bootstrap** over all sessions, zero-trade days included);
   - deterministic (fixed seeds), with unit tests for the fill model and for look-ahead (prefix invariance).
4. **A frozen spec file** (JSON) with a version id. Nothing in it may change after submission; a change is a new
   version and goes back to the start of the queue.

## 6. How a strategy passes

On the holdout, with the frozen code and no changes:
- ≥100 trades (intraday) or ≥40 trades across ≥3 years (multi-day);
- average R > 0 **and** the 95% day-block interval above 0;
- still positive at 2× costs (and, for multi-day, at 1.5× financing);
- positive in at least 2 of 3 equal chronological thirds of the holdout;
- account-level: positive after combining with the other candidates under one shared risk budget.

Then it runs forward on the practice account at 0.10% risk for at least 60 trading days before any live money.

## 7. Directions we would like you to research

Not a list of winners — a starting queue. Prefer ideas with published, out-of-sample evidence and a reason to
persist, and check whether that evidence survives CFD costs.

**Multi-day / longer horizon**
- Time-series momentum / trend following across a diversified set of OANDA instruments (indices, metals,
  energy, FX, bonds if offered), volatility-scaled positions, daily signals.
- FX carry (and carry + trend), with OANDA financing actually charged.
- Cross-sectional momentum or value across FX majors.
- Seasonality with published support (turn-of-month in equity indices, pre-holiday effects) — net of financing.

**Intraday**
- Intraday momentum around the US open/close (e.g. the first half-hour predicting the last half-hour) — note the
  bot currently flattens at 15:50 NY; say if a strategy needs that changed.
- Volatility-regime filters that decide **whether** to trade at all on a given day, applied to simple entries.
- Overnight vs intraday return decomposition on indices and gold (where the drift actually accrues).
- Anything else with real evidence — but no indicator stacking without incremental evidence, no pattern
  libraries, no influencer claims.

## 8. Ground rules

- Develop only on `dev_*` data. Do not request, infer or reconstruct holdout prices.
- No tuning after seeing a holdout score. A changed rule is a new version.
- Report everything that was tried. A negative result is a useful result.
- Prefer few parameters and wide plateaus over sharp optima.
- Say plainly when the honest answer is "no edge found".
