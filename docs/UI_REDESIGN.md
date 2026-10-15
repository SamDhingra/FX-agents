# Trading workspace redesign — local review

Base: `SamDhingra/FX-agents`, `main` at `18fdae07b9ee7626a073e882d5370093210fb023`.
Local branch: `ui/trading-workspace-redesign`. No push, pull request or deployment performed.

## What changed

The existing nine-page FastAPI dashboard remains one self-contained HTML file. No frontend framework or build is needed in production. External Google Fonts requests were removed; typography uses the device's system fonts.

- Grouped navigation: Workspace, Research, Monitoring. Page descriptions clarify the purpose of each screen.
- Updated light and dark palettes, quieter cards, clearer headings, consistent buttons and numeric formatting.
- Overview prioritizes account metrics, performance, operational conditions and positions; open positions appear first after the metrics on phones. Instrument bias cards stack on phones instead of hiding instruments in horizontal swipes.
- Trades provides text search, result/instrument/timeframe filters, sorting, a filtered summary and an export for the selected book. Search covers the latest 400 loaded trades; CSV exports the book's full available journal, not the filtered view. Instrument and strategy summaries are collapsible.
- Visible account environment on mobile. The book selector distinguishes Practice, Simulation, Live account and virtual books.
- Connection freshness is separate from entry permission. A lost/stale connection shows a warning and disables pause/resume/flatten. Only received snapshots reset freshness; resizing or changing theme does not.
- Flatten uses a native confirmation dialog naming the environment and number of open positions. It retains the existing server semantics: pause entries and request all positions closed. A response is described as request acceptance, not a guarantee of execution.
- Pending control requests disable repeat clicks. Network and authorization errors give feedback. Returning to the selected book clears old values until its new snapshot arrives.
- Keyboard focus, a skip link, drawer/sheet focus containment, Escape dismissal and keyboard-activated trade rows.

## Implementation boundaries

Production changes are confined to `fxagents/dashboard/static/index.html`. Strategy logic, risk checks, execution, server APIs and authentication remain unchanged. Existing calendar, compare, playbook, strategy, backtest, news and agent features are retained and restyled.

The separate preview uses synthetic fixtures. It does not contact GitHub, a broker or the running app. Its controls modify in-memory sample state. Research pages without fixtures show their existing empty states. It is a visual/interaction review, not evidence of returns or a live deployment.

## Verification

- Baseline: 221 Python tests passed.
- After redesign: 221 Python tests passed.
- Required three-day synthetic simulation completed with exit code 0 and no tracebacks.
- Chromium: all nine pages exercised at 1440, 768 and 390 pixels. No page-level horizontal overflow or JavaScript errors in the tested states.
- Search, sorting, trade timeline drawer, themes, mobile More menu, book switching, pause/resume, canceled/confirmed flatten, stale connection and empty equity/position states exercised with intercepted HTTP/WebSocket traffic.
- Desktop, mobile and dark mode screenshots inspected locally.

Live broker execution and production data integration have not been exercised. Research states requiring populated backtests/playbook were retained but only their empty states and navigation were tested in the browser.

## Review and reproduce

Open the accompanying `FX-agents-design-preview.html` in a browser. It includes its own sample data and works offline.

UI fixtures and checks live in `tests/ui/`. With Playwright and Chromium available:

```bash
node tests/ui/smoke.cjs
node tests/ui/build-preview.cjs /tmp/FX-agents-design-preview.html
```

The smoke script accepts `CHROMIUM_PATH` for a locally installed Chromium. Browser-test dependencies are development tools and are not production dependencies. Generated screenshots/previews belong in `docs/ui-review/` and should not be deployed or committed as app code.

Review the local diff against the stated base before applying. If the upstream HTML has changed, rebase and repeat the UI checks. Rollback consists of restoring the original dashboard HTML. Push and deployment require separate approval.

## Alternate glass themes and motion

The follow-up adds an Appearance dialog, while retaining all three layouts in the same app:

- **Frost:** light translucent panels, pearl/lilac ambient background and a floating navigation rail.
- **Aurora:** dark translucent panels, restrained violet and blue ambient color, and stronger text contrast.
- **Studio:** the solid surface option, available in either light or dark mode using the sun button.

Iris, Ocean and Amber accents are selectable independently. Theme, surface, accent and motion preferences persist on the device. Glass is the default finish; the existing light/dark preference is preserved.

Transparency is confined to spacious surfaces and navigation. Tables, dialogs and drawers use solid fills. Backdrop blur is limited to navigation and dialog backdrops; the page background is static. No extra runtime dependencies or network assets were added.

Motion is purposeful and short: 200 ms page entry, 180 ms panel opening, 160 ms control feedback and 230 ms drawer movement. Financial values, incoming snapshots and charts are not animated. The old continuous trading-status pulse was removed. A user motion-off switch and OS reduced-motion settings disable animation and smooth scrolling, including pseudo-elements.

Verification: all 221 Python tests pass; the nine-page browser smoke suite passes at 1440/768/390 px. `tests/ui/appearance.cjs` checks the three presets at 1440/390 px, accent selection, persistence across reload, user/OS reduced motion, focus return and absence of KPI animation on new snapshots. Desktop and phone screenshots were inspected. The required three-day synthetic simulation completed successfully.

```bash
node tests/ui/appearance.cjs
node tests/ui/build-preview.cjs /tmp/FX-agents-glass-preview.html
```

No GitHub push or deployment has been made.

## v3 signature panels (Oct 2026)

Read-only additions; nothing here changes trading.

- **Overview:** a "what it's waiting for" line (entry windows, flatten, gold's overnight range, next high-impact news, all counting down), **market weather** per instrument (sea = Choppiness Index, wind = higher-timeframe bias, storm = news, wave speed = volatility percentile) and a **risk fuel** gauge (today's loss budget left, drawdown vs the kill switch).
- **Agents → Mission control:** a live map of the agents. Every bus message (`insights.install_tap`, a `*` subscription) travels along its edge as a coloured dot; tap an agent for what it does, its heartbeat and its latest messages.
- **Trade drawer → The case:** the agents' reasoning as a dialogue (market data, strategy, bias, Jev, risk, position manager) with a verdict stamp ("Jev called it / missed"); **Replay** draws the 1-minute candles around the trade with entry, stops, partials, exit and (gold breakout) the range, and can play them back.
- **Compare → Evidence meter** (average R with a day-block bootstrap 95% range, progress ring to 100 trades, per-strategy breakdown), **book race** (cumulative R by trade against a zero-edge luck cone), **fan of futures** (500 resampled 100-trade paths per book: median, 5% case, 95% worst drawdown) and a **day barcode**.
- **Backtests → Strategy journey + graveyard:** every strategy tested, how far it got (idea → dev → holdout → paper → live) and why the dead ones died. The ledger is the `LEDGER`/`GRAVE` constants in `index.html`; update them when a test finishes.

APIs: `/api/now`, `/api/evidence`, `/api/story/{trade_id}`, `/api/bars?symbol&start&end`, and `flow` in the state snapshot. Checks: `tests/test_dashboard_insights.py`, `node tests/ui/v3.cjs`.

## v4: ghost trades, filter scorecard, Ask the bot (Oct 2026)

- **Ghost trades** (`fxagents/dashboard/ghosts.py`): every setup in a book's `signals` table — taken or passed — is played out on the 1-minute bars with one yardstick exit (its own stop, a 1.5R target, or 4 hours / the 15:50 flatten), entering on the first bar after the signal candle closes and paying half the spread. Results go to a `ghosts` table in the same journal every 5 minutes, so they outlive the in-memory bars. Repeats of a setup within 15 minutes count once.
- **Filter scorecard** (Compare page, per book): for each rule that passed setups (bias, news, Jev, risk, position limits, chop filter …) — how many it blocked, their ghost average with a 95% range, "saved/cost" R, and a verdict against the setups that were taken under the same yardstick. Ghosts also appear as faint diamonds on a trade's replay.
- **Ask the bot** (button on every page; `fxagents/dashboard/ask.py`, `POST /api/ask`): gathers the facts for the question (setups and trades around the time asked about, open positions, bias, news, each book's record and scorecard) and, with `ANTHROPIC_API_KEY` in `.env`, Claude answers from those facts only. Without the key the facts are summarised directly. Capped at `dashboard.ask_per_hour` calls.

## v5: time machine, edge atlas, evening recap, home-screen app, slide to flatten, trade notes (Oct 2026)

- **Time machine** (More → Time machine; `/api/timeline?day=`): one book's day — equity, 5-minute candles, trades with their events, every setup seen and why it was taken or passed, Jev decisions, news — on a minute slider with play at ×60/×300/×1200. Days older than the in-memory bars (≈2 weeks) show the journal events without candles.
- **Edge atlas** (Strategies; `/api/atlas`): the setup map as instrument × setup × hour bubbles: colour = expectancy shrunk toward the setup's own record, size = trades, fade = little data, ring = |t| ≥ 2 — with how many rings luck alone would draw among that many cells.
- **Evening recap** (Overview "Recap", Calendar day "Recap"; `/api/recap?day=&ai=`): the day per book, a short script read aloud by the browser, a shareable image, and an optional Claude-written version (needs `ANTHROPIC_API_KEY`).
- **Home-screen app**: `manifest.webmanifest`, icons, `sw.js` (network-first; caches only the page shell and icons, never `/api` or `/ws`), "Add to Home Screen" in More, pull-to-refresh inside the installed app.
- **Slide to flatten**: on touch screens the flatten confirmation is a slider (a half slide does nothing); mouse/keyboard keep the button.
- **Trade notes**: notes with quick tags and dictation in every trade, saved to that book's journal and searchable on the Trades page.

## v6: calm overview, new type, theme packages (Oct 2026)

- **Overview**: equity first (big Bricolage Grotesque figure that counts to the new value when it changes, the day's change, a full-bleed equity line with 1D/1W/All), then open positions (a new one slides in once), then today in four numbers, then "Coming up" as a quiet list with the evening recap. Market watch, strategy selection and trading conditions (with the loss-budget gauge) follow. Market weather was removed. On phones the overview heading drops its description lines.
- **Type**: Geist for the interface, Bricolage Grotesque for figures and titles, both self-hosted (`static/fonts`, OFL licences alongside; served from `/fonts/*.woff2`, no third-party requests).
- **Theme packages** (Appearance): Ink & Brass (navy, brass), Mint Paper (cool white, banker green), Carbon (graphite, cobalt) beside Frost, Aurora and Studio. They are solid skins (`data-skin`) with their own palettes; accent colours apply to the classic three.
