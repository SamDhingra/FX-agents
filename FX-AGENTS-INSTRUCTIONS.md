# FX-Agents: Instructions & Playbook

A reference for running, changing, and reusing the FX-Agents multi-agent intraday trading bot
(XAUUSD, S&P 500, Nasdaq 100, Dow 30). It is written for two readers:

* **You**, when you come back to the project in a month and need to remember how it works.
* **An AI coding assistant** (Claude Code etc.). Drop this file in the repo root, or paste
  sections 2–7 into `CLAUDE.md`, and the assistant will follow the project's rules.

> **Status when this was written (2026-09-28).** The system has run end to end on a *synthetic*
> market with a paper broker, and 16 unit tests pass. It has **not** been run against a real
> IB Gateway, and Jev has only been tested against a stubbed response. Sim P&L is meaningless,
> because the simulated market is a random walk. Treat every result as plumbing verification,
> not evidence of edge, until paper trading on real data says otherwise.

---

## 1. What it is (one paragraph)

Nine agents talk over an in-process message bus. MarketData ingests 1-minute bars. News and Bias
build context. The Strategist backtests strategies continuously and evolves them. The Selector
asks Jev which strategy suits each symbol this hour. The Trader finds setups and has Jev grade
them. Risk is the final gate before the Broker. PositionManager runs the 1:1 → partial → stop to
profit → pyramid logic. Journal, Notifier and Monitor record, alert and guard. A FastAPI
dashboard shows all of it on phone and laptop.

```
IBKR / Sim ─► MarketData ─► bar_1m ─► PositionManager ─► Broker (IBKR | Paper)
                  │                         ▲   ▲
                  └─► bar_signal (5m/15m) ─► Trader ─► Risk ┘
                                             ▲
   News ─┐                                   │
   Bias ─┼─► state ─► Selector (hourly, Jev-rated picks)
   Strategist (evaluate · tune · create · promote/demote) ─► stats ─► Selector
   Journal (SQLite) · Notifier (ntfy/Telegram) · Monitor (kill switch) · Dashboard
```

---

## 2. Non-negotiable rules (invariants)

These are enforced in code and covered by tests. **Never weaken them without being told to.**
If a change would break one, stop and ask.

1. **Every trade has a stop.** No stop → no order. Enforced in `Risk` *and again* in `broker.guard_entry`.
2. **Stop distance ≤ 10% of trade value** (`risk.max_stop_pct_of_trade_value`).
3. **Stops only move toward profit.** `broker.guard_stop_move` rejects anything else.
4. **Size by risk, not by conviction:** a full stop-out costs ≤ `risk_per_trade_pct` (0.5%) of equity,
   scaled by the bias/news multipliers. The 10% rule is only an outer bound.
5. **Hard higher-timeframe bias rule.** Trade only with the composite Daily/4H/1H bias
   (`side × score ≥ bias.min_align`). Exceptions exist only via the controlled reversal
   exception (section 6).
6. **Pyramid adds must never risk open profit.** An add is refused if being stopped right after it
   would make the trade net negative. No adds during a news blackout, in reversal-exception or
   neutral-reduced trades.
7. **Nothing enters during a news blackout;** tier-1 days trade at half size.
8. **Flat by `sessions.flatten_at`** (15:50 NY). This is a day-trading system.
9. **Kill switch:** −2% day or −6% from peak → flatten everything and halt.
10. **No look-ahead.** Every indicator, swing and HTF bar is used only once it is confirmed/closed.
    `test_strategies_scan_without_lookahead` and `test_bias_frame_is_causal` guard this.
11. **One `scan()` per strategy** feeds live trading, the hourly evaluation and the learner.
    Never fork "live" and "backtest" versions; they will drift apart.
12. **Live mode requires `--i-understand-live-trading`.** Paper first, always.
13. **Trading never blocks on the network.** Jev has a timeout and a local heuristic fallback.

---

## 3. Quick start

```bash
cd fx-agents
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q                       # must be green before anything else
python main.py                            # sim: synthetic market, paper broker, dashboard :8088
python main.py --days 14 --speed 0.05     # longer / slower replay (seconds per simulated minute)
python backtest.py --synthetic --days 30  # leaderboard + expectancy by hour
```

**Sim mode needs no accounts.** It replays this week's real USD news calendar (shifted onto the
simulated days) so the news logic is exercised too.

### CLI reference

| Command | Purpose |
|---|---|
| `python main.py [--mode sim\|paper\|live]` | Run all agents. `FX_MODE` env var also works |
| `--days N` | Sim: trading days to replay |
| `--speed S` | Sim: seconds per simulated minute (0 = as fast as possible) |
| `--port P`, `--db PATH`, `--config PATH` | Dashboard port, journal file, config file |
| `--no-dashboard`, `--exit-after-sim` | Headless runs (CI, quick checks) |
| `--i-understand-live-trading` | Required with `--mode live` |
| `python backtest.py --synthetic\|--csv SYM=file.csv\|--ibkr --days N` | Leaderboard; `--no-bias` and `--no-pyramid` for A/B comparisons |

### Environment variables (`.env`, never committed)

`TYPESAFE_API_KEY` (Jev) · `DASHBOARD_TOKEN` · `TV_WEBHOOK_SECRET` · `NTFY_TOPIC` ·
`TELEGRAM_BOT_TOKEN` · `TELEGRAM_CHAT_ID` · `FX_MODE`. Env vars override `config.yaml`.

---

## 4. Going from sim → IBKR paper → live

1. **IB Gateway (paper account).** Configure → API → Settings: enable socket clients, port
   **4002**, *uncheck* read-only, add `127.0.0.1` to trusted IPs.
2. **Market data.** Defaults are CME micro futures (MGC, MES, MNQ, MYM). They need CME/COMEX/CBOT
   real-time data. Without it, set `ibkr.market_data_type: 3` (delayed) and use it for testing
   only. Spot-gold and index-CFD alternatives are in `config.yaml`; check your IBKR account can
   trade them.
3. **Backtest on real history first:** `python backtest.py --ibkr --days 30` (needs ≥ 25 days so Daily
   structure exists). Compare with `--no-bias`.
4. **Fill in `.env`,** then `python main.py --mode paper`.
5. **Paper for at least 2–4 weeks.** Read the journal daily. Check: stops are resting at IBKR, the
   day rolls at 17:00 NY, news blocks fire, notifications arrive, no "unprotected position" alerts.
6. **Futures roll:** the continuous contract resolves to the front month at start-up. **Restart after
   each roll** (equity indices quarterly, micro gold bimonthly).
7. **Live only after paper shows a real edge over a meaningful number of trades:**
   `python main.py --mode live --i-understand-live-trading` (port 4001). Start with a fraction of
   intended size.

Keep it running on a Mac with `deploy/com.sam.fxagents.plist` (launchd), and prevent the Mac from
sleeping on power. **In the cloud (recommended):** follow `DEPLOY-CLOUD.md`. That's Lightsail in
ca-central-1 running Docker Compose with `ib-gateway` (IBC), `fxagents` and `cloudflared`, behind
Cloudflare Access at `trade.advanceanalytics.net`. Operate it with `./fx.sh up | logs | status |
update | backup | pause | flatten`. Use a dedicated IBKR username for the bot; for live, approve
the weekly 2FA re-login on IBKR Mobile.

---

## 5. Architecture map: where things live

```
config.yaml                  every tunable (instruments, risk, sessions, management, bias, news, jev…)
main.py                      wiring: builds ctx, starts agents, dashboard, feed
backtest.py                  CLI leaderboard (synthetic | TradingView CSV | IBKR)
fxagents/
  bus.py  state.py  models.py  config.py       plumbing (pub/sub, live state, Position/Signal/Bar)
  data.py                    BarStore, SimFeed, IBKRFeed (1m bars + 1h history)
  indicators.py              EMA/RSI/MACD/ATR/ADX, swing pivots (with known_at), resampling
  bias.py                    Daily/4H/1H structure, PDH/PDL, Asia range, premium/discount
  news.py                    calendar: feed, tiers, windows, pre-news actions, event-day risk
  jev.py                     Jev (TypeSafe) questions + heuristic fallback + decision logging
  sim.py                     trade simulator (mirrors live management), stats, synthetic market
  broker.py                  PaperBroker, IBKRBroker (bracket entry + resting GTC stop)
  journal.py                 SQLite: trades, decisions, signals, strategy versions, equity, learner log
  strategies/                base.py · smc.py · classic.py · __init__.py (registry, Confluence)
  agents/                    trading.py · context.py · strategist.py · ops.py · core.py
  dashboard/                 server.py (FastAPI + WebSocket) · static/index.html (single-page app)
tests/test_core.py           16 tests: risk guards, pyramid maths, no look-ahead, news, bias, Jev parsing
deploy/                      launchd + systemd units
```

**Message topics (bus):** `bar` → `bar_1m` / `bar_signal{tf}` · `clock` · `stats_updated` · `selection` ·
`entry_request` · `position_opened/updated/closed` · `stop_filled` · `pre_news` · `flatten_all/symbol` ·
`alert` · `decision` · `promotion` · `daily_summary` · `tv_signal` · `feed_done`.
Handlers run **in subscription order and are awaited**, so ordering (stops → management → new
entries) is deterministic. Keep it that way.

---

## 6. How the important pieces behave

### Strategies

| id | Idea |
|---|---|
| `ict_fvg_sweep` | Liquidity sweep → MSS → FVG retrace in a killzone, 1H bias filter |
| `ict_ote` | 62–79% retrace of the impulse leg after MSS |
| `dtfx_zone` | Dave Teaches FX: the BOS leg is the zone (30/50/70%), confirmed rejection |
| `stoic_sbs` | Stoic Trader Swing Breakout Sequence (double bottom/top, optional Golden SBS 61.8%) |
| `smc_order_block` | Last opposing candle before a displacement leg that breaks structure |
| `smc_breaker` | Swept swing → MSS → retest of the breaker |
| `smc_ifvg` | Inverse FVG retest |
| `smc_liquidity_sweep` | PDH/PDL/Asia raid → CHoCH |
| `sr_rejection`, `rsi_pullback`, `macd_cross` | Classic S/R, RSI, MACD |

Every strategy runs on **5m and 15m** (ids look like `smc_ifvg:15m@v1`). Learner-made strategies
are `primary+filter:tf@vN` (Confluence) or tuned `name:tf@vN`.

**Not implemented yet:** mitigation blocks, balanced price ranges, SMT divergence, weekly/monthly opens.

### Bias and its safeguards (`bias.py`, `agents/context.py`)

Score = 0.40·Daily + 0.35·4H + 0.25·1H structure (±1 each), bias counts only if `side × score ≥ 0.25`.
Neutral → no trades (`bias.neutral_policy: skip|reduced`). When the bias may be wrong:

1. 1H is in the score, so a 1H break cuts conviction the same hour.
2. **Circuit breaker:** 2 aligned losses in a row → symbol's bias suspended until the 1H structure breaks again.
3. **Jev audit** (hourly, near sessions): "is this bias still valid?" Low → **in doubt**: half size, only setups graded ≥ 0.7.
4. **Reversal exception** (Risk agent): counter-bias only if a liquidity pool was raided **and** 1H already
   flipped **and** Jev reversal ≥ 0.7 → half size, 1:1, no pyramiding.
5. **Accuracy tracking:** hit-rate of the bias over the next 4 hours, shown on the dashboard.

### News (`news.py`, `NewsAgent`)

Forex Factory weekly JSON (USD only), refreshed hourly, cached to `data/news_cache.json`.
Tier 1 (FOMC, NFP, CPI, PCE, Fed Chair…): no entries −30/+30 min; protect winners (stop to breakeven+)
or close others 5 min before; half size all day. High: ±15 min. Medium: ±5 min. Heads-up push
30 min ahead. Add one-offs under `news.manual_events`. If the feed is unreachable it falls back to the
cache, then to manual events only. **Check that the feed loads from your machine.**

### Trade management (`PositionManagerAgent`, mirrored in `sim.simulate_outcome`)

Initial stop → at **1R** bank 50%, stop → +0.1R (into profit) → each further +1R: trail the stop one
step and consider a Jev-confirmed pyramid add (max 2, 50% size each). If you change this logic,
change `sim.py` in the same commit, or backtests stop reflecting live behaviour.

### Jev usage (`jev.py`)

Jev is a **judge, not a router**. Code builds a compact state, asks typed questions, and ordinary
code decides. Question types: **Score** (5 levels → 0–1, plus confidence) and **Noul** (yes/no probability).

| Decision | Kind | Used by |
|---|---|---|
| `strategy_rating` (per strategy) + `trade_ok` | Score / Noul | Selector, hourly |
| `signal_rating` + `htf_aligned` | Score / Noul | Trader, per setup |
| `pyramid_continuation` | Noul | PositionManager, per add |
| `bias_audit`, `reversal_exception` | Noul | Bias agent / Risk |
| `candidate_review` | Noul | Strategist, per new strategy version |

Blend: `w·(conf·jev + (1−conf)·stats) + (1−w)·stats` (`jev.weight`). No key / timeout / error → local
heuristic, decision tagged `source: heuristic`. Every call is stored in `decisions` (inputs → outputs).
*This differs from the custom LLM harness*, where Jev routes tasks across models; here it never
generates text and never routes.

### Strategist lifecycle

Hourly: re-backtest every live/shadow version per symbol × timeframe (with the bias rule applied,
so stats only count trades that could really be taken). Daily 17:05 NY and at start-up: tune
parameters/R:R and build confluence strategies on the first 70% of data, validate on the last 30%,
Jev reviews for overfit. New versions start in **shadow**; **promoted only** after beating their
parent on trades made *after* creation. Losing live versions demote (≥ 2 always stay live).

### Dashboard

`http://localhost:8088/?token=<DASHBOARD_TOKEN>` (cookie remembered). Pages: Overview (KPIs, news
banner, bias cards, positions with R-progress, picks, equity), **P&L calendar** (green/red days,
monthly totals, day drill-down, news dots), Trades (filters, timeline drawer), Strategies, News,
Agents & Jev. Pause / Resume / Flatten need the token. Reach it privately (Tailscale); if exposed via a
tunnel, add an access layer in front. Endpoints: `/api/state`, `/api/calendar`, `/api/day/{date}`,
`/api/trades`, `/api/signals`, `/api/decisions`, `/api/journal.csv`, `/ws`, `/webhook/tradingview`.

### TradingView

Alerts POST JSON to `/webhook/tradingview` (needs `secret`). They are treated as one more strategy:
graded by Jev, sized/gated by Risk (a missing stop gets a 1-ATR stop). Execution is always IBKR.
Exports (Export chart data) feed `backtest.py --csv SYMBOL=file.csv`.

---

## 7. How to work on this codebase (rules for humans and AI assistants)

**Before changing anything:** run `python -m pytest -q`. After: run it again, plus
`python main.py --no-dashboard --exit-after-sim --days 3 --db data/scratch.sqlite` and confirm no tracebacks.

**When changing risk, sizing, stops, bias or news:** add or update a test *first*. Then re-run a multi-day
sim and re-check the invariants against the journal (stops never move backward, every pyramid
`worst_case ≥ 0`, aligned trades satisfy the bias threshold, stop ≤ 10%).

**Style and conventions**
* Strategies subclass `Strategy`, implement `_scan(df, ctx) -> list[RawSignal]` for the **long** side using
  `_mirror()` so shorts are generated symmetrically. Use `known_at`-aware pivots only.
* Signals trigger on the **close** of bar `i`; entry = close, stop is structural (+ATR buffer).
* Config over constants: new knobs go in `config.yaml` with a comment, not in code.
* Agents communicate through the bus. Do not call one agent from another.
* Anything that leaves the machine (orders, notifications) must be safe to fail: log, alert, keep going.
* Keep the dashboard a single self-contained HTML file; test at 390 px and 1440 px width.

**Recipes**

*Add a strategy:* subclass in `strategies/smc.py` or `classic.py`, set `name`, `family`, `description`,
`default_params`, `param_grid`; add to `BUILTIN`; add a smoke test (signals > 0 on synthetic data and
no look-ahead); run `backtest.py --synthetic`. It appears on both timeframes automatically.

*Add an instrument:* add it under `instruments` (contract, multiplier, tick size, commission,
`max_units`, sim price/vol). Everything else is data-driven.

*Add a timeframe:* add it to `timeframes.entry`. Existing journals keep old strategy ids, so start a fresh
`storage.db_path` or expect old versions to be ignored.

*Add a Jev question:* add a method in `jev.py` with (1) the typed question, (2) a deterministic fallback,
(3) a call through `_ask` so it is logged. Never let the answer bypass a hard rule; Jev may only make
things more conservative or select among allowed options.

*Add a news source / currency:* extend `news.currencies`, `tier1_keywords`, or `manual_events`.

*Add a dashboard page:* add a `<section class="page" id="p-x">`, a title in `titles`, a nav entry
(sidebar + tab bar) and a render function called from `render()`.

**Do not**
* Make Risk or the broker guards optional "for testing".
* Read future bars in a strategy, or tune parameters on the out-of-sample split.
* Compare results across different bias/news settings without saying so.
* Trust sim P&L, synthetic backtests, or a handful of trades.
* Commit `.env`, `data/`, API keys or tokens.

---

## 8. Operating routine

**Daily (paper/live)**
* Before the open: dashboard → Overview (bias cards, news banner). Anything tier-1 today? Half size is automatic.
* After 16:05 NY: read the daily summary; open the Calendar and review each trade's timeline.
* Look at **skipped/rejected signals** (Journal → signals): are the bias/news filters removing good
  trades or bad ones?

**Weekly**
* Strategies page: which versions were promoted/demoted? Read the learner log.
* Bias accuracy per symbol. If it sits near 50% for a symbol, that symbol's bias is adding little.
* Compare live expectancy (journal) with the backtest for the same strategies. A large gap means slippage,
  a bug, or overfitting.

**Monthly:** review `config.yaml` changes, roll futures if needed, update the news tier keywords, back up
`data/journal.sqlite`.

**If something looks wrong:** hit **Pause** (stops new entries), then **Flatten** if needed. Check
`Agents & Jev` for a silent agent, and the alert feed for "unprotected position" or "data stale".
Resting stops at IBKR stay in place even if the app dies.

---

## 9. Known limitations and next steps

* Not yet run against real IB Gateway or a live Jev key. Expect small fixes on first contact.
* Backtests fill at the signal bar's close and check stops first within a bar (conservative), but
  they do not model spread widening or partial fills.
* Prior-day/Asia levels use the CME 17:00 trading day; verify they match your chart's session settings.
* Missing SMC concepts: mitigation blocks, balanced price ranges, SMT divergence, weekly/monthly opens.
* Ideas: per-symbol Jev weight, news-surprise (actual vs forecast) handling, a sim of spread/slippage
  by hour, walk-forward promotion, a mobile "kill" widget.

---

## 10. Reusing this for other projects

The reusable patterns, in order of usefulness:

1. **Agents on a deterministic async bus** with ordered handlers: easy to add/replace an agent, easy to test.
2. **Single `scan()` for live, evaluation and learning** so research and production cannot diverge.
3. **Hard rules enforced twice** (policy layer + execution layer) with tests, and a model that can only
   tighten them.
4. **Shadow → forward-tested → promoted** for any self-modifying component; never promote on in-sample results.
5. **Model as judge with a deterministic fallback:** typed questions, confidence, blend with statistics,
   log every decision's inputs and outputs, never block on the network.
6. **Causality tests** (`truncate the data → same past signals`) for anything time-series.
7. **Journal everything, including what you skipped and why.**
8. **A dashboard with tokens, a kill button, and a phone layout** from day one.

**Starter prompt for a new, related project** (paste into Claude Code with this file in the repo):

> Read `FX-AGENTS-INSTRUCTIONS.md`. I want a new bot for `<market/instruments>` reusing its architecture:
> the async bus, single-`scan()` strategies, hard risk invariants enforced in Risk and the broker, Jev as a
> judge with heuristic fallback, shadow-then-promote learning, SQLite journal, and the responsive dashboard.
> Start in sim mode with tests for the invariants and a causality test, and tell me which of the rules in
> section 2 you would change and why *before* changing them.

---

*Disclaimer: this is software, not financial advice. Automated trading can lose money quickly. Keep it on
paper until the journal shows an edge over a meaningful number of trades, and never risk money you cannot
afford to lose.*
