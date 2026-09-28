# FX-Agents

A multi-agent intraday trading system for **XAUUSD (gold), S&P 500, Nasdaq 100 and Dow 30**.
It uses ICT, Dave Teaches FX, Stoic Trader SBS, S/R, RSI and MACD strategies. Each hour Jev
picks the best-rated strategy for each symbol. Trades start at 1:1 R:R, pyramid into winners
and move the stop into profit. There is a trade journal and a live dashboard that works on
phone and laptop.

> **Status:** it has run end-to-end on a synthetic market with a paper broker, and 10 unit tests
> pass. The IBKR execution path is written against `ib_async`, but it has **not** been run
> against your IB Gateway yet. Run `--mode paper` for at least 2–4 weeks before you consider live.
> The P&L numbers from sim mode are meaningless, because the market in sim mode is a random walk.

---

## The agents

```
             ┌──────────── bus (asyncio pub/sub) ─────────────┐
 IBKR / Sim ─► MarketData ─► bar_1m ─► PositionManager ─► Broker (IBKR / Paper)
                    │                        ▲   ▲
                    └─► bar_5m ─► Trader ─► Risk ┘   │
                                    ▲                 │
      Strategist ─stats─► Selector ─┘ (hourly pick)   │
      (evaluate · tune · create · promote/demote)     │
                                                      │
      Journal (SQLite) · Notifier (ntfy/Telegram) · Monitor (kill switch, health)
                          │
                    Dashboard (FastAPI + WebSocket)
```

| Agent | What it does |
|---|---|
| **MarketData** | Stores 1-minute bars. It lets the broker check resting stops first, then sends out 1m and 5m events. |
| **Strategist** *(never trades)* | Re-backtests every strategy version each hour, per symbol, overall and **by hour of day**. Once a day (and at start-up) it **tunes** parameters and R:R and **creates** new *confluence* strategies (for example SBS entries filtered by the DTFX structure bias). New versions run in **shadow** and are **promoted** only after they beat their parent on forward trades. Losing live versions are demoted. |
| **Selector** | A few minutes before each hour, Jev rates every live strategy per symbol and gives a confidence. That rating is blended with hour-of-day stats, and the best one is activated. A symbol can also **sit the hour out**. |
| **Trader** | Runs the active strategy on each 5-minute close. Jev grades each setup (A+…D plus a confidence), and weak setups are skipped. TradingView alerts come in here too. |
| **Risk** | The hard gate: stop required, stop ≤ **10% of trade value**, size = 0.5% of equity at risk, max positions, entry windows, news blackouts, kill switch. |
| **PositionManager** | At **1R**, it banks 50% and moves the stop to **+0.1R (in profit)**. At each further +1R it trails the stop up one step and **pyramids** (only if Jev rates continuation as likely **and** the worst case after the add is still ≥ $0). All positions are flattened at 15:50 NY. |
| **Journal** | SQLite store of every trade, every management event (partial, stop move, pyramid), every Jev decision (inputs → outputs), every signal taken or skipped with the reason, and the equity curve. |
| **Notifier** | Push notifications to your phone (ntfy and/or Telegram) for entries, exits, stop-to-profit, pyramids, kill switch, promotions and the daily summary. |
| **Monitor** | Kill switch at −2% for the day or −6% from the equity peak. Flattens any broker position that has no working stop. Alerts on stale data or silent agents. Rolls the day at 17:00 NY. |

### Strategies (in `fxagents/strategies/`)
| id | Model |
|---|---|
| `ict_fvg_sweep` | ICT Silver-Bullet style: liquidity sweep → displacement through structure (MSS) → entry on the FVG retrace, inside killzones, with 1H bias |
| `ict_ote` | ICT Optimal Trade Entry: 62–79% retrace of the impulse leg after an MSS, killzones only |
| `dtfx_zone` | Dave Teaches FX: the leg that broke structure becomes the zone (30/50/70%). Entry on a confirmed rejection, stop beyond the origin |
| `stoic_sbs` | Stoic Trader Swing Breakout Sequence: breakout → first tap → scalp high → liquidate first tap → double bottom → entry on the break (optional "Golden SBS" 61.8% filter) |
| `sr_rejection` | Clustered swing-point S/R levels (≥2 touches), entry on a rejection candle |
| `rsi_pullback` | RSI recovery from the pullback threshold, with the EMA200 trend |
| `macd_cross` | MACD signal-line cross on the correct side of zero, aligned with EMA50 |
| *learner-made* | `primary+filter@vN` confluence strategies and tuned `name@vN` versions |

Each strategy has **one** `scan()` implementation, used for live trading, hourly evaluation and
learning, so backtests and live signals can't drift apart. A test checks that `scan()` never
looks ahead.

---

## Quick start (5 minutes, no accounts)

```bash
cd fx-agents
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py                        # sim: 3 synthetic days, dashboard on http://localhost:8088
python -m pytest -q                   # 10 tests: risk guards, pyramiding math, no look-ahead, Jev parsing
python backtest.py --synthetic        # leaderboard + expectancy by hour
```

## Going to IBKR paper

1. **IB Gateway** (or TWS): log in to the **paper** account. Go to Configure → API → Settings:
   enable socket clients, set port **4002**, *uncheck* read-only API, and add 127.0.0.1 as a trusted IP.
2. **Market data:** the default contracts are CME micro futures (MGC, MES, MNQ, MYM). They need
   CME/COMEX/CBOT real-time data (the non-pro CME bundle is cheap). With no subscription, set
   `ibkr.market_data_type: 3` (delayed); that is OK for testing only.
   *Spot gold / index CFDs:* alternate contract lines are in `config.yaml`. Check with IBKR
   Canada whether your account can trade them.
3. Copy `.env.example` to `.env` and fill in `TYPESAFE_API_KEY`, `DASHBOARD_TOKEN`, and your ntfy or Telegram details.
4. `python backtest.py --ibkr --days 20` checks each strategy on real history first.
5. `python main.py --mode paper`

Live needs `python main.py --mode live --i-understand-live-trading` and port 4001.

**Futures roll:** the continuous contract resolves to the front month at start-up. Restart the
app after each roll: equity index futures roll quarterly (Mar/Jun/Sep/Dec); micro gold rolls bimonthly.

## Phone + laptop dashboard

* On the Mac it runs at `http://localhost:8088`. From your iPhone over **Tailscale**, use
  `http://<your-mac>.<tailnet>.ts.net:8088/?token=<DASHBOARD_TOKEN>` once. The token is then kept
  in a cookie, and you can use Share → *Add to Home Screen* to get an app icon.
* The dashboard shows KPIs, open positions (R now, 🔒 when the stop is in profit, adds), this hour's
  pick per symbol with the Jev/stat blend, the equity curve (hover or touch), the strategy leaderboard
  (overall, last 36h, this hour), the journal (tap a trade for its full event log, CSV export),
  Jev decisions, the learner log, alerts and agent health.
* The **Pause / Resume / Flatten all** buttons need the token.
* If you ever expose it through your Cloudflare tunnel, put **Cloudflare Access** in front as well.

## Jev (TypeSafe)

Jev is used the same way as in the custom harness. Code builds a compact state, and Jev answers typed questions:
* `strategy_rating`: a **Score** (5 levels) per strategy for this symbol and hour, plus a **Noul** `trade_ok`
* `signal_rating`: a setup-grade Score plus a Noul for "aligned with HTF"
* `pyramid_continuation`: a Noul, "likely to extend another 1R?"
* `candidate_review`: a Noul, "is this out-of-sample improvement real or overfit?"

The value is blended with the stats as `weight × (conf × jev + (1 − conf) × stats) + (1 − weight) × stats`.
If there is no key, or the call times out, a transparent heuristic answers instead. The decision
is tagged `heuristic` and trading never waits on the network. Expect roughly 40–60 strategy-rating
calls per trading day, plus one per signal and per pyramid check.

## TradingView

Your subscription is used in two ways: (1) **alerts → webhook**, and (2) **CSV exports for backtests**.

Alert webhook URL: `https://<your-host>/webhook/tradingview`. The message looks like this:
```json
{"secret":"<TV_WEBHOOK_SECRET>","symbol":"NDQ","side":"{{strategy.order.action}}",
 "price":{{close}},"stop":{{plot("stop")}},"strategy":"my_pine_model"}
```
Alerts are treated as one more strategy. They are graded by Jev and sized and checked by Risk. If an
alert has no stop, a 1-ATR stop is attached, because no trade goes out without one. TradingView
cannot reach your Mac directly, so the webhook needs a public HTTPS route (your Cloudflare tunnel).
Execution always goes through IBKR.

Backtest on TradingView data: chart → *Export chart data* → `python backtest.py --csv NDQ=export.csv`.

## Risk rules (enforced twice: in the Risk agent and in the broker layer)

* No stop means no order. A stop on the wrong side means no order. A stop wider than **10% of trade value** means no order.
* Stops only ever move toward profit. At IBKR the stop is a real resting **GTC STP** child order,
  so the position stays protected if the app or the laptop goes down.
* **Also added:** size so that a full stop-out costs ≤ **0.5% of equity**. On leveraged futures a 10%
  price stop alone could be many times your account, so the 10% rule is the outer bound and the
  0.5% rule is the one that actually binds.
* A pyramid add is refused if being stopped right after the add would turn the trade negative.
* Kill switch: −2% day or −6% from peak → flatten and halt.

## Files

```
config.yaml            all settings (instruments, risk, sessions, management, Jev, notifications)
main.py                runs every agent (sim | paper | live)
backtest.py            leaderboard + expectancy by hour (synthetic | TradingView CSV | IBKR)
fxagents/strategies/   smc.py (ICT, DTFX, SBS) · classic.py (S/R, RSI, MACD) · confluence builder
fxagents/agents/       trading.py · strategist.py · ops.py
fxagents/sim.py        management-accurate trade simulator + stats + synthetic market
fxagents/jev.py        Jev scorer with heuristic fallback
fxagents/broker.py     PaperBroker, IBKRBroker (bracket entry + resting GTC stop)
fxagents/journal.py    SQLite journal
fxagents/dashboard/    FastAPI server + single-page responsive UI
deploy/                launchd plist (Mac, always-on) · systemd unit (Linux / Lightsail)
```

## Honest notes

* This is **intraday algorithmic** trading on 1–5 minute bars, not HFT. Python plus the IBKR API
  adds latency in the tens to hundreds of milliseconds. That is fine for these setups; it would not work for tick scalping.
* The ICT / DTFX / SBS rules are mechanical interpretations of discretionary methods. Check a
  sample of signals on TradingView against how you read them, then adjust the parameters.
* Nothing here is financial advice. Automated trading can lose money quickly. Keep it on paper
  until the journal shows an edge across a meaningful number of trades.
