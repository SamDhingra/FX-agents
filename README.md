# FX-Agents

A multi-agent intraday trading system for **XAUUSD (gold), S&P 500, Nasdaq 100 and Dow 30**.
It uses ICT, Dave Teaches FX, Stoic Trader SBS, S/R, RSI and MACD strategies. Each hour Jev
picks the best-rated strategy for each symbol. Trades start at 1:1 R:R, pyramid into winners
and move the stop into profit. There is a trade journal and a live dashboard that works on
phone and laptop.

> **Status:** it has run end-to-end on a synthetic market with a paper broker, and 34 unit tests
> pass. Two live brokers are supported: **OANDA** (default; v20 REST API) and **IBKR** (`ib_async`).
> Both are tested against fakes only: neither has yet traded on your real practice/paper account.
> Run `--mode paper` for at least 2–4 weeks before you consider live.
> The P&L numbers from sim mode are meaningless, because the market in sim mode is a random walk.

---

## The agents

```
             ┌──────────── bus (asyncio pub/sub) ─────────────┐
 OANDA/IBKR/Sim ─► MarketData ─► bar_1m ─► PositionManager ─► Broker (OANDA / IBKR / Paper)
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
| **Bias** | Tracks the **Daily / 4H / 1H** market-structure bias for each symbol, plus premium/discount, PDH/PDL and the Asia range, and runs the safeguards below. |
| **News** | Keeps the economic calendar (Forex Factory feed) up to date. It blocks entries around releases, protects open trades just before them, halves size on tier-1 days and sends heads-ups. |
| **Selector** | A few minutes before each hour, Jev rates every live strategy per symbol and gives a confidence. That rating is blended with hour-of-day stats, and the best **5m** strategy and the best **15m** strategy are activated. A symbol can also **sit the hour out**. |
| **Trader** | Runs the active strategy on each 5-minute close. Jev grades each setup (A+…D plus a confidence), and weak setups are skipped. TradingView alerts come in here too. |
| **Risk** | The hard gate: stop required, stop ≤ **10% of trade value**, size = 0.5% of equity at risk, max positions, entry windows, news blackouts, kill switch. |
| **PositionManager** | At **1R**, it banks 50% and moves the stop to **+0.1R (in profit)**. At each further +1R it trails the stop up one step and **pyramids** (only if Jev rates continuation as likely **and** the worst case after the add is still ≥ $0). All positions are flattened at 15:50 NY. |
| **Journal** | SQLite store of every trade, every management event (partial, stop move, pyramid), every Jev decision (inputs → outputs), every signal taken or skipped with the reason, and the equity curve. |
| **Notifier** | Push notifications to your phone (ntfy and/or Telegram) for entries, exits, stop-to-profit, pyramids, kill switch, promotions and the daily summary. |
| **Monitor** | Kill switch at −2% for the day or −6% from the equity peak. Flattens any broker position that has no working stop. Alerts on stale data or silent agents. Rolls the day at 17:00 NY. |

### Strategies (in `fxagents/strategies/`)
| id | Model |
|---|---|
| `smc_order_block` | SMC order block: the last opposing candle before a displacement leg that breaks structure (optionally with an FVG). Entry on the first return into it |
| `smc_breaker` | Breaker block: a swing low is swept, then the swing high breaks (MSS). The last up-candle before the sweep becomes the breaker. Entry on the retest |
| `smc_ifvg` | Inverse FVG: an opposing gap that is closed through by a displacement candle flips polarity. Entry on the retest |
| `smc_liquidity_sweep` | Liquidity raid of PDH/PDL or the Asia high/low, a close back inside, then a CHoCH on the entry timeframe |
| `ict_fvg_sweep` | ICT Silver-Bullet style: liquidity sweep → displacement through structure (MSS) → entry on the FVG retrace, inside killzones, with 1H bias |
| `ict_ote` | ICT Optimal Trade Entry: 62–79% retrace of the impulse leg after an MSS, killzones only |
| `dtfx_zone` | Dave Teaches FX: the leg that broke structure becomes the zone (30/50/70%). Entry on a confirmed rejection, stop beyond the origin |
| `stoic_sbs` | Stoic Trader Swing Breakout Sequence: breakout → first tap → scalp high → liquidate first tap → double bottom → entry on the break (optional "Golden SBS" 61.8% filter) |
| `sr_rejection` | Clustered swing-point S/R levels (≥2 touches), entry on a rejection candle |
| `rsi_pullback` | RSI recovery from the pullback threshold, with the EMA200 trend |
| `macd_cross` | MACD signal-line cross on the correct side of zero, aligned with EMA50 |
| *learner-made* | `primary+filter@vN` confluence strategies and tuned `name@vN` versions |

Every strategy runs on **both 5-minute and 15-minute** bars (`name:5m@v1`, `name:15m@v1`). The two
versions compete in the hourly selection and are tuned separately by the Strategist.

Mitigation blocks, balanced price ranges, SMT divergence and weekly/monthly opens are **not** included yet.

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
python -m pytest -q                   # 34 tests: risk guards, pyramiding, no look-ahead, Jev, OANDA adapter
python backtest.py --synthetic        # leaderboard + expectancy by hour
```

## Going to OANDA practice (default broker)

1. In the OANDA hub, open your **practice** account → **Manage API Access** → generate a token.
2. Copy `.env.example` to `.env` and set `OANDA_API_TOKEN`, `OANDA_ACCOUNT_ID` (the practice
   account ID), plus `TYPESAFE_API_KEY`, `DASHBOARD_TOKEN` and your ntfy or Telegram details.
3. `python check_oanda.py` is a **read-only** check: account, instruments, precision, prices.
4. `python main.py --mode paper` trades the practice account. Instruments are the CFDs `XAU_USD`,
   `SPX500_USD`, `NAS100_USD`, `US30_USD` (set per symbol under `oanda:` in `config.yaml`).

Every entry carries its stop (`stopLossOnFill`), each pyramid add is its own OANDA trade with the
same stop, and stop fills are picked up by polling open trades every ~15 s. Live: a live token
and account ID, then `python main.py --mode live --i-understand-live-trading`.

## Going to IBKR paper (`--broker ibkr`, needs futures permission)

1. **IB Gateway** (or TWS): log in to the **paper** account. Go to Configure → API → Settings:
   enable socket clients, set port **4002**, *uncheck* read-only API, and add 127.0.0.1 as a trusted IP.
2. **Market data:** the default contracts are CME micro futures (MGC, MES, MNQ, MYM). They need
   CME/COMEX/CBOT real-time data (the non-pro CME bundle is cheap). With no subscription, set
   `ibkr.market_data_type: 3` (delayed); that is OK for testing only.
   *Spot gold / index CFDs:* alternate contract lines are in `config.yaml`. Check with IBKR
   Canada whether your account can trade them.
3. Copy `.env.example` to `.env` and fill in `TYPESAFE_API_KEY`, `DASHBOARD_TOKEN`, and your ntfy or Telegram details.
4. `python backtest.py --ibkr --days 20` checks each strategy on real history first.
5. `python main.py --mode paper --broker ibkr` (or `broker: ibkr` in `config.yaml`)

Live needs `python main.py --mode live --broker ibkr --i-understand-live-trading` and port 4001.

**Futures roll:** the continuous contract resolves to the front month at start-up. Restart the
app after each roll: equity index futures roll quarterly (Mar/Jun/Sep/Dec); micro gold rolls bimonthly.

## Running it in the cloud

See **[DEPLOY-CLOUD.md](DEPLOY-CLOUD.md)**. The setup is the same as the Jev app: AWS Lightsail
(Canada Central) with Docker Compose running IB Gateway (headless, IBC), the agents and
cloudflared, behind a Cloudflare Tunnel with Cloudflare Access email codes. Nothing is exposed
directly to the internet. `./fx.sh up` starts everything.

## Phone + laptop dashboard

* On the Mac it runs at `http://localhost:8088`. From your iPhone over **Tailscale**, use
  `http://<your-mac>.<tailnet>.ts.net:8088/?token=<DASHBOARD_TOKEN>` once. The token is then kept
  in a cookie, and you can use Share → *Add to Home Screen* to get an app icon.
* **Overview:** equity with a sparkline, today's P&L, the news countdown or blackout banner, a
  bias card per symbol (D/4H/1H, score gauge, premium/discount, accuracy, Jev audit), open
  positions with an R-progress bar (🔒 when the stop is in profit), this hour's 5m and 15m picks,
  and the equity curve.
* **P&L calendar:** month grid. **Green days** are net profitable and **red days** net losing,
  with deeper tint for bigger days. Dots mark tier-1 and high-impact news. There are monthly
  totals and a daily P&L bar chart, and you can tap a day to see its trades and events.
* **Trades:** filter by symbol, result or timeframe, then tap a trade for its full timeline.
* **Strategies:** leaderboard (filter by symbol or 5m/15m) and the learning log.
* **News**, and **Agents & Jev** (agent health, every Jev decision, activity).
* On a phone it has a bottom tab bar and can be installed as an app. It supports light and dark
  themes, and toasts pop up for new alerts.
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
Execution goes through the configured broker (OANDA or IBKR).

Backtest on TradingView data: chart → *Export chart data* → `python backtest.py --csv NDQ=export.csv`.

## Higher-timeframe bias: a hard rule, with safeguards

**Rule:** every strategy may only trade in the direction of the composite bias. The score is
0.40 × Daily + 0.35 × 4H + 0.25 × 1H structure, and the trade needs side × score ≥ 0.25. If the
timeframes disagree, the bias is NEUTRAL and there are no trades (set `neutral_policy: reduced`
for half size instead). The Strategist's backtests apply the same rule, so the hourly rankings
only count trades that could actually be taken.

**When the bias is wrong:**
1. **Fast invalidation.** 1H structure is part of the score, so a 1H break against the daily cuts
   conviction the same hour instead of waiting for the daily candle.
2. **Loss circuit-breaker.** Two bias-aligned losses in a row on a symbol suspend its bias until
   the 1H structure prints a fresh break.
3. **Jev audit.** Every hour near a session, Jev is asked whether the bias is still valid. If it
   says probably not, the bias is IN DOUBT: half size, and only A-grade setups (≥ 0.7).
4. **Controlled reversal exception.** A counter-bias trade is allowed only after a liquidity pool
   (PDH/PDL/Asia) was raided, the 1H structure has already flipped the trade's way, **and** Jev
   rates it a genuine reversal (≥ 0.7). It trades at half size, 1:1, with no pyramiding.
5. **Accuracy tracking.** How often the bias called the next 4 hours correctly is shown on each
   symbol's bias card.

## News

* **Tier 1** (FOMC, NFP, CPI, PCE, Fed Chair): no entries from 30 minutes before to 30 after.
  Five minutes before the release, winners get their stop moved to breakeven+ and everything
  else is closed. Size is halved for the whole day.
* **High impact:** no entries 15/15 minutes; open trades are protected 2 minutes before.
* **Medium impact:** no entries 5/5 minutes.
* A push notification goes out 30 minutes ahead. Upcoming events are included in every Jev rating,
  and the dashboard shows a countdown banner.
* Windows, keywords, currencies and manual events are all set in `config.yaml` → `news`.

## Risk rules (enforced twice: in the Risk agent and in the broker layer)

* No stop means no order. A stop on the wrong side means no order. A stop wider than **10% of trade value** means no order.
* Stops only ever move toward profit. The stop always rests at the broker (OANDA: a GTC stop-loss
  created with the fill; IBKR: a GTC STP child order), so the position stays protected if the app or
  the server goes down.
* **Also added:** size so that a full stop-out costs ≤ **0.5% of equity**. On leveraged futures a 10%
  price stop alone could be many times your account, so the 10% rule is the outer bound and the
  0.5% rule is the one that actually binds.
* A pyramid add is refused if being stopped right after the add would turn the trade negative.
* Kill switch: −2% day or −6% from peak → flatten and halt.

## Files

```
config.yaml            all settings (instruments, risk, sessions, management, Jev, notifications)
main.py                runs every agent (sim | paper | live) on OANDA or IBKR
check_oanda.py         read-only OANDA connection check
backtest.py            leaderboard + expectancy by hour (synthetic | TradingView CSV | IBKR)
fxagents/strategies/   smc.py (ICT, DTFX, SBS) · classic.py (S/R, RSI, MACD) · confluence builder
fxagents/agents/       trading.py · strategist.py · ops.py
fxagents/sim.py        management-accurate trade simulator + stats + synthetic market
fxagents/jev.py        Jev scorer with heuristic fallback
fxagents/broker.py     PaperBroker, IBKRBroker (bracket entry + resting GTC stop)
fxagents/oanda.py      OandaFeed + OandaBroker (v20 REST, stopLossOnFill, per-trade stops)
fxagents/journal.py    SQLite journal
fxagents/dashboard/    FastAPI server + single-page responsive UI
deploy/                launchd plist (Mac, always-on) · systemd unit (Linux / Lightsail)
```

## Honest notes

* This is **intraday algorithmic** trading on 1–15 minute bars, not HFT. Python plus a broker API
  adds latency in the tens to hundreds of milliseconds. That is fine for these setups; it would not work for tick scalping.
* The ICT / DTFX / SBS rules are mechanical interpretations of discretionary methods. Check a
  sample of signals on TradingView against how you read them, then adjust the parameters.
* Nothing here is financial advice. Automated trading can lose money quickly. Keep it on paper
  until the journal shows an edge across a meaningful number of trades.
