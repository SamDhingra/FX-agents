# Deploying FX-Agents to the cloud

This uses the same setup as the Jev app (`jev.advanceanalytics.net`): **AWS Lightsail in Canada
Central (ca-central-1)** running **Docker Compose**, reached only through a **Cloudflare Tunnel**
with **Cloudflare Access email codes** in front. Nothing is exposed directly to the internet.

The default broker is **OANDA** (practice account for paper, live account later). The bot talks
to OANDA's REST API with your API token, so there is no gateway to run, no daily restart and no
weekly phone approval. IBKR remains available (appendix A) once futures are enabled there.

```
 phone / laptop ──HTTPS──► Cloudflare Access (email one-time PIN)
                                   │
                          Cloudflare Tunnel (outbound only)
                                   │
 ┌──────────── Lightsail · Ubuntu 24.04 · Docker Compose ─────────┐
 │  cloudflared ──► fxagents:8088 (agents + dashboard) ───────────│──HTTPS──► OANDA v20 API
 │                        │ ./data/journal.sqlite                 │          (practice / live)
 └────────────────────────────────────────────────────────────────┘
 TradingView alerts ──► /webhook/tradingview (Access bypass, TradingView IPs only)
```

**Use a separate instance from the Jev app.** This box holds your broker token. The Jev app runs
model-written code for several users, so keep the two isolated. You can reuse the same Cloudflare
account, domain and one-time-PIN login.

**Cost:** with OANDA the **2 GB / 2 vCPU plan (US$12/month)** is enough; take the 4 GB plan
(US$24) if `docker stats` shows memory pressure during the strategist's hourly backtests, or if
you later add IB Gateway. Cloudflare Tunnel and Access (up to 50 users) are free. OANDA's cost is
in the spread (no commission, no data fees).

---

## 0. Before you start (OANDA)

1. **Practice account + API token.** In the OANDA hub, open your **practice (demo)** account and
   go to **Manage API Access** → generate a token. Note the **practice account ID** (looks like
   `101-002-1234567-001`). A practice token only works on the practice server, and a live token
   only on live.
2. **Set the practice balance** to roughly what you'd really trade with, if OANDA lets you
   choose it. Sizing is 0.5% of equity per trade, so a huge demo balance makes every trade far
   bigger than you'd run live. A CAD account is fine: the bot converts equity to USD for sizing.
3. **Instruments the bot trades:** `XAU_USD`, `SPX500_USD`, `NAS100_USD`, `US30_USD` (CFDs:
   1 unit = $1 per index point; gold 1 unit = 1 oz). Tick size, unit step and minimum size are read
   from your account at start-up. **Small accounts:** if 0.5% of equity is less than one minimum
   unit × a typical stop, that trade is skipped (logged on the Trades page) rather than
   oversized.
4. **Try it from your Mac first (optional, 2 minutes):** in `~/Claude/fx-agents`, put
   `OANDA_API_TOKEN=…` and `OANDA_ACCOUNT_ID=…` in a file called `.env`, then run
   `pip install -r requirements.txt && python check_oanda.py`. It's **read-only**: it prints the
   account, whether each instrument is tradeable, its precision and the latest price.
   `python main.py --mode paper` then runs the whole bot on the practice account with the
   dashboard on http://localhost:8088.

---

## 1. Create the server (Lightsail console)

1. Lightsail → **Create instance** → Region **Canada (Central) ca-central-1** → **Linux/Unix →
   OS only → Ubuntu 24.04 LTS** → plan **$12 (2 GB)** → name it `fx-agents`.
2. **Networking tab → attach a static IP.**
3. **Networking → IPv4 firewall:** delete the HTTP (80) rule. Keep **SSH (22)** but restrict it to
   **your IP** (or keep only the browser SSH). The tunnel needs no inbound ports at all.
4. **Snapshots tab → enable automatic daily snapshots.**
5. Download the SSH key if it isn't the same `LightsailDefaultKey-ca-central-1.pem` you already use.

## 2. Prepare the server (SSH in once)

```bash
ssh -i ~/.ssh/LightsailDefaultKey-ca-central-1.pem ubuntu@<static-ip>

# Docker + compose plugin
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && newgrp docker

# 2 GB swap (a cushion for pandas), NY time, automatic security updates
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
sudo timedatectl set-timezone America/New_York
sudo apt-get install -y unattended-upgrades sqlite3 && sudo dpkg-reconfigure -f noninteractive unattended-upgrades
```

## 3. Get the code onto the server

**Option A (recommended): a private GitHub repo.** This lets `./fx.sh update` pull changes.

```bash
# on your Mac, inside fx-agents/
git init && git add -A && git commit -m "fx-agents" && gh repo create fx-agents --private --source . --push
# on the server
git clone git@github.com:<you>/fx-agents.git ~/fx-agents     # add the server's SSH key as a deploy key first
```

**Option B: copy the folder.**

```bash
# on your Mac (from ~/Claude)
tar --exclude=.env --exclude=data --exclude=.git -czf fx-agents.tgz fx-agents
scp -i ~/.ssh/LightsailDefaultKey-ca-central-1.pem fx-agents.tgz ubuntu@<static-ip>:~
ssh -i ~/.ssh/LightsailDefaultKey-ca-central-1.pem ubuntu@<static-ip> 'tar -xzf fx-agents.tgz'
```

## 4. Cloudflare Tunnel (Zero Trust dashboard)

1. **Zero Trust → Networks → Tunnels → Create a tunnel → Cloudflared** → name `fx-agents`.
2. On the install screen choose **Docker**. Copy **only the token** (the long string after
   `--token`). You don't run that command; Compose runs cloudflared for you.
3. **Public hostname:** subdomain `trade`, domain **`advanceanalytics.net`** (not `.com`: that's
   the parked domain that broke the Jev deployment). **Service: HTTP → `fxagents:8088`**.
4. Save. The tunnel shows as *Healthy* once step 6 is running.

## 5. Cloudflare Access (who can open the dashboard)

One-time PIN is already enabled at account level from the Jev setup (Settings → Authentication).

1. **Access → Applications → Add → Self-hosted**:
   name `FX-Agents`, domain `trade.advanceanalytics.net`, session duration `24h`.
2. **Policy "Owner" → Action: Allow → Include: Emails** → type your email and **press Enter** so it
   becomes a tag (the same gotcha as last time). Login method: **One-time PIN**.
3. **Only if you use TradingView alerts**, add a second application:
   - Self-hosted, domain `trade.advanceanalytics.net`, **path `webhook/tradingview`**.
   - Policy **Action: Bypass → Include: IP ranges** `52.89.214.238`, `34.212.75.30`, `54.218.53.128`,
     `52.32.178.7` (TradingView's webhook servers).
   - The app still checks `TV_WEBHOOK_SECRET`. TradingView only allows webhooks on accounts with
     2FA enabled, and it times out after 3 seconds; the app acknowledges immediately and processes
     the alert in the background.

The dashboard token (`DASHBOARD_TOKEN`) stays on as a second layer, and Pause / Resume / Flatten
require it.

## 6. Configure and start

```bash
cd ~/fx-agents
cp .env.cloud.example .env && chmod 600 .env
nano .env        # FX_MODE=paper, FX_BROKER=oanda, OANDA_API_TOKEN, OANDA_ACCOUNT_ID (practice),
                 # CF_TUNNEL_TOKEN, TYPESAFE_API_KEY, DASHBOARD_TOKEN (long random), NTFY_TOPIC …
                 # generate secrets with:  openssl rand -hex 24

./fx.sh test     # builds the image and runs the unit tests inside it
./fx.sh check    # read-only OANDA check: account, instruments, prices (no orders)
./fx.sh sim 2    # optional: 2-day simulation in a throwaway container
./fx.sh up       # starts fxagents + cloudflared
./fx.sh logs     # expect: "OANDA practice account …", "NDQ: … historical 1m bars", "dashboard → …"
./fx.sh status
```

Then open **https://trade.advanceanalytics.net/?token=<DASHBOARD_TOKEN>** on your phone. You'll get
an email code the first time, and the token is remembered after that. On iPhone, use
**Share → Add to Home Screen** so it opens like an app.

**Notifications:** install **ntfy** on your phone and subscribe to the topic you put in `NTFY_TOPIC`
(make it long and unguessable). You'll get entries, exits, stop moves into profit, adds, news
heads-ups and kill-switch alerts.

## 7. Daily operation

| When | What |
|---|---|
| Always | Nothing to do. The app runs 24/5 and flattens at 15:50 NY |
| Weekly | `./fx.sh backup` (or add the cron line below); review the Strategies page |
| Code changes | `git push` on your Mac → `./fx.sh update` on the server |
| Emergency | Dashboard **Pause** / **Flatten**, or `./fx.sh pause` / `./fx.sh flatten` over SSH. You can also close trades in the OANDA app; the bot notices within ~15 s and books them |

**Live vs Shadow:** the bot also runs a shadow book (by default the setup-first mode) on the same
live bars with virtual fills; it never sends orders. Compare the two on the dashboard's **Compare**
page, or flip the **Live / Shadow** switch at the top to see the shadow book's positions, calendar and
trades. `./fx.sh backup` copies the main journal; the shadow journal is `data/journal_shadow.sqlite`.

Nightly journal backup (on the server):

```bash
( crontab -l 2>/dev/null; echo '30 17 * * 1-5 cd ~/fx-agents && ./fx.sh backup >/dev/null 2>&1' ) | crontab -
```

**How protection works at OANDA:** every entry is a market order with the stop attached
(`stopLossOnFill`), so OANDA creates the stop in the same transaction as the fill. The bot then
re-reads the trade, and if the stop is somehow missing it closes the trade at once. Each pyramid
add is its own OANDA trade with its own stop; moving the stop moves it on all of them. **Stops rest
at OANDA**, so a crash or restart never leaves a position unprotected. On restart, any open
trade the new process didn't open itself is closed within about a minute (with an alert),
because this is a day-trading system.

## 8. Moving to live (only after weeks of paper that you're happy with)

Generate a **live** API token in the OANDA hub (live tokens differ from practice tokens), then in
`.env`:

```
FX_MODE=live
I_UNDERSTAND_LIVE_TRADING=yes
OANDA_API_TOKEN=<live token>
OANDA_ACCOUNT_ID=<live account id>
```

Run `./fx.sh check --live` (read-only), then `./fx.sh restart fxagents`. Consider temporarily
lowering `risk.risk_per_trade_pct` in `config.yaml` for the first live weeks. The app refuses to
start live without `I_UNDERSTAND_LIVE_TRADING=yes`, and paper mode can never point at the live
server.

## 9. Troubleshooting

| Symptom | Check |
|---|---|
| Tunnel "Down" in Cloudflare | `./fx.sh logs cloudflared`. Usually a wrong or missing `CF_TUNNEL_TOKEN` |
| 502 from trade.advanceanalytics.net | App still starting. `./fx.sh logs`, then `./fx.sh status` |
| "OANDA rejected the token/account" | Practice token used with a live account ID (or the reverse), or a typo. `./fx.sh check` shows which accounts the token can see |
| "instrument … not tradeable on this OANDA account" | Your account/region doesn't offer that CFD. Remove the symbol from `instruments` in `config.yaml` or change its `oanda.instrument` |
| Trades skipped with "unit(s) risk $… > budget" | Account too small for the minimum size at 0.5% risk. Raise `risk.risk_per_trade_pct` slightly or accept fewer trades |
| Orders rejected "INSUFFICIENT_MARGIN" | Lower `max_units` for that symbol in `config.yaml`, or fewer simultaneous positions (`risk.max_open_positions`) |
| Orders rejected mentioning client extensions | Account linked to MT4: set `oanda.client_extensions: false` |
| Stale-data alerts | Weekend or the daily 17:00 NY break are expected. Otherwise check `./fx.sh logs` for OANDA errors |
| Webhook 403 | The Access bypass app for `/webhook/tradingview` is missing, or TradingView's IPs changed (check their docs) |
| Server slow / out of memory | `docker stats`. Move to the 4 GB plan, and confirm swap is on (`swapon --show`) |
| Wrong day boundaries | The server and containers use America/New_York. Check `timedatectl` |

## 10. Security checklist

- [ ] `.env` is `chmod 600`, never committed (`.gitignore` covers it), and all secrets are long and random
- [ ] Lightsail firewall: no HTTP/HTTPS rules; SSH restricted to your IP
- [ ] Access policy allows only your email; the webhook bypass is limited to TradingView's IPs and path
- [ ] OANDA: the practice token for paper; generate the live token only when you go live, and revoke tokens you no longer use (hub → Manage API Access)
- [ ] Automatic snapshots on, plus the nightly journal backup
- [ ] ntfy topic name is unguessable (anyone who knows it can read your alerts)

---

## Appendix A — IBKR instead of OANDA

Needs **futures trading permission** on the IBKR account (Client Portal → Settings → Account
Settings → Trading Permissions; margin account required) and the CME/COMEX/CBOT real-time data
subscriptions for MGC, MES, MNQ, MYM.

1. **Paper first, on your own account.** The paper account has its **own username**, so the
   gateway doesn't kick you off TWS or IBKR Mobile. Client Portal → Settings → **Paper Trading
   Account**: note the paper username, set its password, turn on **"Share real-time market data
   subscriptions with paper trading account"**, and reset the paper balance to a realistic amount.
   Shared data goes to one session at a time, so watching charts on your live login can starve
   the bot of real-time data; set `ibkr.market_data_type: 3` (delayed) temporarily if needed.
2. In `.env`: `FX_BROKER=ibkr`, `COMPOSE_PROFILES=ibkr`, `TRADING_MODE=paper`, `IB_PORT=4004`,
   `TWS_USERID` / `TWS_PASSWORD` = the paper login. `./fx.sh up` then also starts the
   `ib-gateway` container (IBC, headless); watch it log in with `./fx.sh logs ib-gateway`.
   Use the 4 GB server plan (the gateway is Java and needs about 1 GB).
3. **Live:** a dedicated second username for the bot (one session per username), `TRADING_MODE=live`,
   `IB_PORT=4003`. Live logins need **IBKR Mobile 2FA**: the gateway restarts daily at 17:05 NY
   without 2FA, but about once a week (usually Sunday) you approve a full re-login on your phone.
4. After each futures roll: `./fx.sh restart fxagents` so the front-month contract is picked up.
5. Troubleshooting: "IBKR … not ready" = gateway not logged in (credentials, pending 2FA, or the
   username is logged in elsewhere). See the gateway's login screen with `VNC_SERVER_PASSWORD` set,
   `./fx.sh restart ib-gateway`, then `./fx.sh vnc`.

---

### Files for the cloud deployment

| File | Purpose |
|---|---|
| `Dockerfile` | App image: Python 3.11-slim, non-root user, health check on `/healthz` |
| `docker-compose.yml` | `fxagents`, `cloudflared`, and `ib-gateway` only with `COMPOSE_PROFILES=ibkr`; no public ports |
| `.env.cloud.example` | Every setting and secret the stack needs |
| `fx.sh` | `up`, `down`, `logs`, `status`, `update`, `test`, `check`, `sim`, `backup`, `pause`, `resume`, `flatten`, `vnc` |
| `check_oanda.py` | Read-only OANDA connection check (account, instruments, precision, prices) |
| `.dockerignore` | Keeps `.env`, `data/` and `.git` out of the image |
