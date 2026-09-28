# Deploying FX-Agents to the cloud

This uses the same setup as the Jev app (`jev.advanceanalytics.net`): **AWS Lightsail in Canada
Central (ca-central-1)** running **Docker Compose**, reached only through a **Cloudflare Tunnel**
with **Cloudflare Access email codes** in front. Nothing is exposed directly to the internet.

```
 phone / laptop ──HTTPS──► Cloudflare Access (email one-time PIN)
                                   │
                          Cloudflare Tunnel (outbound only)
                                   │
 ┌──────────── Lightsail · Ubuntu 24.04 · Docker Compose ────────────┐
 │  cloudflared ──► fxagents:8088 (agents + dashboard) ──► ib-gateway │──► IBKR
 │                        │ ./data/journal.sqlite    (IBC, headless)  │
 └────────────────────────────────────────────────────────────────────┘
 TradingView alerts ──► /webhook/tradingview (Access bypass, TradingView IPs only)
```

**Use a separate instance from the Jev app.** This box holds broker credentials and runs a Java
gateway that needs about 1 GB of memory. The Jev app runs model-written code for several users,
so keep the two isolated. You can reuse the same Cloudflare account, domain, and one-time-PIN
login method.

**Cost:** Lightsail 4 GB / 2 vCPU / 80 GB is **US$24 per month**. The 2 GB plan (US$12) works
for paper trading, but it's tight once the strategist's hourly backtests run next to IB Gateway.
Cloudflare Tunnel and Access (up to 50 users) are free. IBKR market data is billed separately
by IBKR.

---

## 0. Before you start (IBKR)

1. **Use a dedicated IBKR username for the bot.** IBKR allows one login session per username.
   If the bot uses the same username you use on TWS or your phone, logging in elsewhere will
   kick the gateway off. To add one: Client Portal → Settings → **Users & Access Rights** → add
   a user with trading permission for your account. Each username needs its own market-data
   subscriptions.
2. **Paper first.** Get the paper username and password from Client Portal → Settings →
   **Paper Trading Account**. Enable "share real-time market data with paper account" for the
   bot's username.
3. **Market data:** the CME/COMEX/CBOT real-time data needed for the micro futures
   (MGC, MES, MNQ, MYM).
4. **2FA (live only):** a live login needs approval in **IBKR Mobile**. The gateway restarts every
   day at 17:05 NY (`IB_AUTO_RESTART_TIME`, during the CME break when the bot is flat) and does
   not need 2FA for those restarts. **About once a week (usually Sunday) IBKR forces a full
   login, and you tap Approve on your phone.** If you miss it, the app alerts you that data is
   stale, and the stops already resting at IBKR stay in place.

---

## 1. Create the server (Lightsail console)

1. Lightsail → **Create instance** → Region **Canada (Central) ca-central-1** → **Linux/Unix →
   OS only → Ubuntu 24.04 LTS** → plan **$24 (4 GB)** → name it `fx-agents`.
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

# 2 GB swap (a cushion for Java + pandas), NY time, automatic security updates
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

**Option B: copy the zip.**

```bash
scp -i ~/.ssh/LightsailDefaultKey-ca-central-1.pem fx-agents.zip ubuntu@<static-ip>:~
ssh ... 'sudo apt-get install -y unzip && unzip fx-agents.zip'
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
nano .env        # FX_MODE=paper, TRADING_MODE=paper, IB_PORT=4004, TWS_USERID/TWS_PASSWORD (paper),
                 # CF_TUNNEL_TOKEN, TYPESAFE_API_KEY, DASHBOARD_TOKEN (long random), NTFY_TOPIC …
                 # generate secrets with:  openssl rand -hex 24

./fx.sh test     # builds the image and runs the unit tests inside it
./fx.sh sim 2    # optional: 2-day simulation in a throwaway container (no IBKR needed)
./fx.sh up       # starts ib-gateway, fxagents, cloudflared
./fx.sh logs ib-gateway     # wait for the login to complete (1–2 min)
./fx.sh logs                # app: "connected to IBKR … accounts […]", history loaded, bias computed
./fx.sh status
```

Then open **https://trade.advanceanalytics.net/?token=<DASHBOARD_TOKEN>** on your phone. You'll get
an email code the first time, and the token is remembered after that. On iPhone, use
**Share → Add to Home Screen** so it opens like an app.

**Notifications:** install **ntfy** on your phone and subscribe to the topic you put in `NTFY_TOPIC`
(make it long and unguessable). You'll get entries, exits, stop moves into profit, adds, news
heads-ups, kill-switch alerts, and "IBKR disconnected" messages.

## 7. Daily operation

| When | What |
|---|---|
| Always | Nothing to do. The app runs 24/5, flattens at 15:50 NY, and the gateway restarts at 17:05 NY |
| Sunday evening (live only) | Approve the IBKR Mobile 2FA prompt when the weekly re-login happens |
| After each futures roll | `./fx.sh restart fxagents` so the front-month contract is picked up |
| Weekly | `./fx.sh backup` (or add the cron line below); review the Strategies page |
| Code changes | `git push` on your Mac → `./fx.sh update` on the server |
| Emergency | Dashboard **Pause** / **Flatten**, or `./fx.sh pause` / `./fx.sh flatten` over SSH |

Nightly journal backup (on the server):

```bash
( crontab -l 2>/dev/null; echo '30 17 * * 1-5 cd ~/fx-agents && ./fx.sh backup >/dev/null 2>&1' ) | crontab -
```

**What happens on restarts:** Docker restarts crashed containers automatically. If the gateway
drops the connection, the app alerts you, exits, and comes back up. On start-up it retries the
gateway for up to 10 minutes while it logs in. **Stops always rest at IBKR**, so a restart never
leaves a position unprotected. Because this is a day-trading system, any position the new
process didn't open itself is detected and closed within about a minute (you get an alert when
that happens).

## 8. Moving to live (only after weeks of paper that you're happy with)

In `.env`, using the **dedicated live username**, set:

```
FX_MODE=live
TRADING_MODE=live
IB_PORT=4003
I_UNDERSTAND_LIVE_TRADING=yes
TWS_USERID=<bot username>
TWS_PASSWORD=<bot password>
```

Then run `./fx.sh down && ./fx.sh up`, approve the IBKR Mobile prompt, and watch
`./fx.sh logs ib-gateway`. Consider temporarily lowering `risk.risk_per_trade_pct` in
`config.yaml` for the first live weeks.

## 9. Troubleshooting

| Symptom | Check |
|---|---|
| Tunnel "Down" in Cloudflare | `./fx.sh logs cloudflared`. Usually a wrong or missing `CF_TUNNEL_TOKEN` |
| 502 from trade.advanceanalytics.net | App still starting (it waits for the gateway). `./fx.sh logs`, then `./fx.sh status` |
| App logs repeat "IBKR … not ready" | Gateway not logged in: `./fx.sh logs ib-gateway`. Wrong credentials, a pending 2FA, or the username is logged in elsewhere |
| Need to see the gateway's login screen | Set `VNC_SERVER_PASSWORD`, `./fx.sh restart ib-gateway`, then `./fx.sh vnc` shows the SSH-tunnel command |
| "competing live session" / kicked off | The same username is logged in on TWS or mobile. Use the dedicated bot username |
| No market data / stale-data alerts | Missing CME subscription, or data not shared with the paper account. Temporarily set `ibkr.market_data_type: 3` |
| Webhook 403 | The Access bypass app for `/webhook/tradingview` is missing, or TradingView's IPs changed (check their docs) |
| Server slow / out of memory | `docker stats`. Move to the 4 GB plan, and confirm swap is on (`swapon --show`) |
| Wrong day boundaries | The server and containers use America/New_York. Check `timedatectl` |

## 10. Security checklist

- [ ] `.env` is `chmod 600`, never committed (`.gitignore` covers it), and all secrets are long and random
- [ ] Lightsail firewall: no HTTP/HTTPS rules; SSH restricted to your IP
- [ ] Access policy allows only your email; the webhook bypass is limited to TradingView's IPs and path
- [ ] Dedicated IBKR username for the bot, with 2FA enabled on the live account
- [ ] VNC password left empty except while troubleshooting (and VNC is bound to localhost only)
- [ ] Automatic snapshots on, plus the nightly journal backup
- [ ] ntfy topic name is unguessable (anyone who knows it can read your alerts)

---

### Files added for the cloud deployment

| File | Purpose |
|---|---|
| `Dockerfile` | App image: Python 3.11-slim, non-root user, health check on `/healthz` |
| `docker-compose.yml` | `ib-gateway` (ghcr.io/gnzsnz/ib-gateway, IBC), `fxagents`, `cloudflared`; no public ports |
| `.env.cloud.example` | Every setting and secret the stack needs |
| `fx.sh` | `up`, `down`, `logs`, `status`, `update`, `test`, `sim`, `backup`, `pause`, `resume`, `flatten`, `vnc` |
| `.dockerignore` | Keeps `.env`, `data/` and `.git` out of the image |

App changes for running in containers: environment overrides for `IB_HOST`, `IB_PORT`,
`IB_CLIENT_ID`, `IB_ACCOUNT`, `DASHBOARD_PORT` and `FX_DB_PATH`; up to 10 minutes of connection
retries while the gateway logs in; exit-and-restart when IBKR disconnects; closing of broker
positions the app isn't managing; an immediate response to TradingView webhooks; and
`I_UNDERSTAND_LIVE_TRADING=yes` as the environment-variable version of the live-trading flag.
