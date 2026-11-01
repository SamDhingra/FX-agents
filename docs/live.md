# The live site (real money)

The live site is a separate copy of the bot. It trades your live OANDA account and has its own sign-ins, data
folder and address. The practice bot and its dashboard stay exactly as they are.

## What runs where

| | Practice (`~/fx-agents`, branch `main`) | Live (`~/fx-live`, branch `live`) |
|---|---|---|
| Account | OANDA practice | OANDA **live** |
| Real orders | — | **NDQ only**, from the same books as practice: hourly pick + C10 on the account; gold and US30 are view-only |
| Paper books | all of them | Playbook + chop filter |
| Playbook (paper book) | re-selected automatically | **frozen**: changes only with `./fx.sh live promote-playbook` |
| Risk | 0.5% per trade, 3 open | 0.25% per trade, 1 open, −1% day halts (`config.live.yaml`) |
| Sign-in | dashboard token | user name + password + **authenticator code** |
| Backtests, Backtester | yes | removed (their endpoints answer 404) |
| Data | `data/` | `data_live/` (journal, users, members; nothing shared) |
| Secrets | `.env` | `.env.live` (live OANDA key, `LIVE_VAULT_KEY`) |

## Promoting code to live

The `live` branch only receives what you choose. Nothing reaches it automatically.

- **Promote everything from main:** `git checkout live && git merge --ff-only main && git push`
- **Promote one change:** `git checkout live && git cherry-pick <commit> && git push`
- **Deploy on the server:** `cd ~/fx-live && ./fx.sh live update`

`config.live.yaml` is the place for live-only settings. Change it on the `live` branch.

## First-time setup (server)

```
cd ~ && git clone -b live https://github.com/SamDhingra/FX-agents.git fx-live && cd fx-live
./fx.sh live setup                     # makes .env.live (chmod 600), the vault key, data_live/
nano .env.live                         # your LIVE OANDA token + account id
./fx.sh live promote-playbook          # copies ~/fx-agents/data/playbook.json after showing what changes
./fx.sh live up                        # builds and starts the live container
./fx.sh live add-owner sam             # your password + the authenticator key (shown once)
```

Then, in the Cloudflare Zero Trust dashboard (Networks, Tunnels, your tunnel, Public hostnames), add
`live.<your-domain>` with service `http://fxlive:8088`. Put a Cloudflare Access policy on it, like the practice site.
Members get through Access too, so add their e-mails to it.

**Back up the vault key.** Keep `LIVE_VAULT_KEY` from `.env.live` in your password manager. Without it, the stored
member keys and authenticator secrets can't be read.

## Security

- **Sign-in.** Password (scrypt) plus a 6-digit authenticator code, and each code works only once. Five failures lock
  that name and address for 15 minutes.
- **Sessions.** A random cookie (HttpOnly, Secure, SameSite=Lax, 30 days). Only its hash is stored.
- **Requests that change something** need an `x-fx` header, which cross-site forms can't send, and a same-host Origin.
  Every one is written to the audit log (Members page).
- **Turning member copying on or off** and changing the member risk cap need a fresh authenticator code.
- **Member OANDA keys** are checked once with OANDA, then stored encrypted (Fernet, key in `.env.live` only). Only the
  last 4 characters are ever shown. Keys are never logged, never sent to a page, and never put in a prompt.
- **Members** see only their own account, their own copies, and the bot's trades in R. They never see your balance or
  your controls.
- **The broker route.** Every order, including your one-tap controls, goes through the Risk agent and position manager,
  as before. Stops only move toward profit.

## Members and copying

1. **Invite.** Members, New invite. You get a one-time link, valid 72 h. Send it privately.
2. **Join.** The member opens it, picks a user name and password, and adds the authenticator key.
3. **Connect.** The member adds their OANDA account id and API token in Settings.
4. **Limits.** The member sets their risk per trade (at most your cap, 1% by default), maximum units and daily loss
   limit.
5. **Consent.** The member ticks the risk statement and switches copying on.
6. **You approve** them, and switch copying on for everyone (authenticator code).

**What gets copied:**
- **Entries:** NDQ entries less than 60 s old, sized from the member's own balance.
- **Stop moves:** the member's stop moves to the same price as yours.
- **Partials:** the same share is closed on the member's account.
- **Closes:** when your trade closes, theirs closes.
- **Not copied:** your pyramid adds.

Members are flattened at 15:50 like you. A member's failure (key revoked, size too small, their own loss limit
reached) is recorded on the Members page and never affects your account or another member.

**Regulation.** Placing trades on other people's accounts may need registration with your securities regulator. In
Canada that's your provincial commission, even for friends and family. Check before switching copying on for anyone
but yourself.

## Live pages (owner)

- **Live desk:**
  - account, today's result and the daily-loss bar
  - Pause entries / Resume / Flatten all (tap twice)
  - each open trade: Close (tap twice), Stop to break-even, Bank 50% / 25%, Move stop, Note
  - before-the-next-trade checklist
  - the bot's latest setups and why it took or skipped them
  - markets: NDQ trading, gold and US30 view-only
- **Journal & review:** tag each trade (followed plan, early entry, moved stop, FOMO …), grade it 1–5 and write the
  lesson. Shows results by habit, by setup and by hour.
- **Compare (live):** the live account next to its paper books, with cumulative R, every book × every instrument, and
  members' copies.
- **Members:** invites, approvals, the copy switch, the audit log.
- **Account security:** sessions, password.
- **Everything else** from the practice dashboard (Overview, Results, Trades, Bias, Playbook, Strategies, News, Agents,
  Time machine) works as before, on live data.
