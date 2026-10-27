# Dynamic trading controller — milestone 1 (shadow review gate)

Registered Oct 26 2026, before any review ran. Source: ChatGPT's dynamic-trading proposal (sections 8–14 of its
bias-filter document) and docs/BACKLOG.md. Milestone 1 changes **no trade**: it records what two independent model
reviewers would have decided about every entry the bot actually takes, and scores those decisions afterwards against
what the trade really did, net of every API call.

## Question

When a setup has passed every deterministic gate (bias, cost cap, news, sessions, risk), would an independent model
review of the frozen chart facts have improved the result by cancelling some entries — net of review costs?

## What is reviewed

Every entry approved by `RiskAgent.on_request` (practice account and the paper books that route through it), at the
moment the position is opened — the same hook as the m15 shadow tag. A daily call budget caps cost; candidates beyond
it are recorded as `not_reviewed: budget`.

## The as-of packet (frozen at the hook, nothing after the entry time)

- identity: candidate id (= position id), book, symbol, side, strategy id, timeframe, entry time (UTC and NY)
- order: entry price, stop, stop distance, target R if any, spread at entry, spread ÷ stop (`cost_r`), instrument
  tick size / price precision
- structural bias: label, score, d / h4 / h1, minutes since the last bias update, h1_minutes / h1_complete
- closed candles only, at instrument precision: the last 24 × M5, 16 × M15, 24 × H1 (OHLC, start time); the forming
  M15 candle separately, labelled partial; the m15_live tag
- levels known at the time: prior-day high/low, Asia high/low, the H4 swing high/low the bias carries
- session: NY time, next scheduled release (FOMC/CPI/NFP/PPI) and minutes to it
- the setup's own record at that moment (trades, avg R) if the journal has it

No chart image in milestone 1 (numeric only); "numeric + chart" is a later, separate arm.

## Reviewers (sealed, concurrent, same packet)

| arm | reviewer | output |
|---|---|---|
| A | none (baseline: every entry taken) | — |
| B | OpenAI model (`dynamic.openai_model`, needs `OPENAI_API_KEY`) | action, evidence, missing data |
| C | Claude model (`dynamic.claude_model`, needs `ANTHROPIC_API_KEY`) | same |
| D | both: enter only if both say ENTER | — |

Structured output (OpenAI JSON schema / Claude forced tool):
`{candidate_id, action: ENTER | WAIT | CANCEL, trigger_id?, invalidation_id?, decisive_evidence (≤ 300 chars),
conflicting_evidence (≤ 300 chars), missing_data (list)}`. `trigger_id` / `invalidation_id` come from a finite menu:
`m15_close_in_direction`, `m5_close_beyond_entry_candle`, `retest_of_entry`; `stop_touched`, `m15_close_against`,
`expiry_30m`. Neither reviewer sees the other's answer. Invalid / late / refused / timed-out replies are `ABSTAIN`
with the reason.

## Scoring (milestone 1 policy: review as a skip gate)

For milestone 1, WAIT counts as "not now": the candidate is skipped in that arm (its trigger is logged for
milestone 2, which will simulate waiting). So per closed trade:

- A: the trade's actual R
- B: actual R if OpenAI said ENTER, else 0 (ABSTAIN → 0, counted separately)
- C: actual R if Claude said ENTER, else 0
- D: actual R if both said ENTER, else 0

Reported per arm: candidates, entered, skipped, total R, R per candidate, avoided losers / missed winners, API cost in
account currency and in R-equivalent, latency p50 / p95 / max, and the share of reviews that arrived within 30 s
(what a live gate could have used). Paired difference of each arm vs A with a 5-weekday block bootstrap once there are
≥ 30 reviewed trades; separate NDQ / US30 / XAUUSD.

## Decision rule (registered now)

After ≥ 100 reviewed closed trades (or at the Nov 5 review, reported as interim): an arm is worth a live trial only if
its paired improvement over A, **after its API cost**, has a 95% range above 0 and its reviews arrive within 30 s for
≥ 95% of candidates. Otherwise it stays in shadow or is dropped. Model or prompt changes start a new arm with a new
version; results are never pooled across versions.

## Engineering contract

- reviews run as background tasks with a hard deadline (`dynamic.deadline_s`, default 25); the bar path never waits
- at most `dynamic.max_concurrency` calls in flight; `dynamic.daily_call_budget` per provider per day
- every request/response logged: provider, model, prompt + schema version, packet hash, latency, tokens, cost, error
- models can't place, change or cancel orders, change config or risk; Risk / PositionManager remain the only route
- missing keys → that arm is off and says so; no key ever written to the journal or prompts

## Milestone 1b — one structured exchange between the reviewers (registered Oct 27 2026, before any exchange ran)

Sam asked for Claude and ChatGPT to talk to each other before deciding. Added as extra shadow arms beside A–D, so the
sealed answers stay recorded and we learn whether talking adds anything.

1. **Round 1 (sealed)** — unchanged: both answer from the same packet without seeing each other.
2. **Round 2 (exchange, once)** — only when both round-1 answers are valid (not ABSTAIN / NOT_REVIEWED). Each gets the
   same packet plus the OTHER reviewer's round-1 answer (action, trigger/invalidation, decisive and conflicting
   evidence, missing data) and gives a final answer in the same schema plus `changed` (bool) and `why_changed`
   (≤ 300 chars, citing packet numbers). No new data, no further rounds; both round-2 calls run concurrently and
   neither sees the other's round-2 answer.
3. **Decision rule (fixed):** both ENTER after round 2 → enter; both WAIT with the same trigger → wait (skipped in
   milestone 1 scoring, as WAIT is); still disagreeing, or any round-2 ABSTAIN → cancel.

Deadline: the whole exchange (round 1 + round 2) must finish within `dynamic.exchange_deadline_s` (default 45); a late
round 2 is ABSTAIN. Round 2 uses the same budget counter (each call counts).

**New arms (scored exactly like B–D):**

| arm | decision |
|---|---|
| E1 | Claude's round-2 answer |
| E2 | OpenAI's round-2 answer |
| E3 | the exchange decision rule above |

Also reported: how often each reviewer changed its mind, which way (toward ENTER or away), and whether the changes
were right (the changed answer's arm result vs its round-1 answer on those trades); latency of the full exchange
(p50/p95, share ≤ 30 s and ≤ 45 s); cost of round 2. E3's main comparison is against D (both agree without talking).

Same decision rule as the other arms: ≥ 100 reviewed closed trades, improvement over A after ALL review costs (round 1
+ round 2) with a 95% range above 0, and the full decision available within 30 s for ≥ 95% of candidates — if the
exchange needs longer than 30 s, it can only ever inform slower (15m+) setups, and the report says so.

### Milestone 1b implementation notes (Oct 27 2026; clarifications only, the design above is unchanged)

- Round-2 prompt version `dyn-x1`, rows in `dyn_reviews` with `round = 2`; `dyn_candidates.exchange_status` (`done` / `skipped: <reason>`),
  `exchange_ms` (round-1 hand-over to round-2 end) and `exchange_decision` (enter / wait / cancel).
- "Same trigger" for WAIT/WAIT means equal and non-null `trigger_id`; two WAITs without a trigger cancel.
- E arms are scored on exchanged candidates only (A and D are shown on the same subset). An E arm's cost is the whole exchange
  that produced its decision: both reviewers' round 1 and round 2 (each answer needs the other's round 1). The 30 s share for the
  rule is taken over all candidates, so candidates where no exchange ran count as not available.
- A round-2 row's `latency_ms` is the round-2 call itself; the full exchange time is `exchange_ms`.
- Round 2 shows each reviewer its own and the other's round-1 answer (Oct 27 2026, before any exchange ran). `changed` is computed locally (action, trigger_id or invalidation_id differs from its round 1); the model's self-report is kept in `changed_reported`, and the stats use the local value.

## Retrospective backfill (Oct 27 2026): the same review on past closed trades

`./fx.sh dynbackfill [book=live] [n=10]` (= `python -m fxagents.dynamic.backfill --book live --last 10`, `--dry-run` to only estimate) runs the milestone-1/1b
review once, by hand, on the book's last N closed trades (`r_multiple` known, newest close first) that have no `dyn_candidates` row yet. N is capped at 50
(more is refused). It needs OANDA_API_TOKEN / OANDA_ACCOUNT_ID, the provider keys and network, so the container is started with `docker compose run` and the
repo's `.env` (like `weekly`), not `exec` (the new code needs the rebuilt image).

- **As-of inputs, from OANDA candles only (read-only).** Per trade: M1 `BA` (bid/ask) complete candles for the 5 days before entry (about 3 trading days), in
  windows that end at the entry minute, so nothing at or after it is requested; H1 `M` candles for the 60 days before entry, keeping only hours that had closed
  by the entry minute. The store object (`RetroStore`) refuses any frame with a candle at or after the entry minute. Spread = ask - bid of the last M1 candle
  before entry; `cost_r` = spread / |entry - initial_stop|; entry, stop, side, strategy from the journal row (`entry`, `initial_stop`, `side`, `strategy`,
  `opened` floored to the minute); `target_r` from the first `partial` event's R when the trade has one; the setup record from the setup's trades that had
  closed before the entry; `m15_live` from the row's shadow tag. The bias is the live computation (`context.compute_bias`, also used by `BiasAgent.compute`) on
  those H1 bars, with `updated` = the entry minute and `h1_minutes` / `h1_complete` counted the same way. `packet.build_packet` is used unchanged.
- **The models are not told.** The packet text is the live format; `source = 'backfill'`, `retrospective = 1` and `reviewed_at` are columns of the
  `dyn_candidates` row only.
- **Same path.** `dynamic/runner.py` (`ReviewRunner`) holds the review coroutine both the live agent and the backfill use: round 1 for both providers
  concurrently, the exchange when both are valid, same prompts, validation, budget counter (counted on the day the calls are made) and deadlines. With no OpenAI
  model or key it runs Claude only and says so (exchange skipped, as live).
- **Scored apart.** The live scorecard, decision rule and `/api/dynamic` top level use `source = 'live'` only. The "Past trades (retrospective, not counted toward
  the decision rule; latency not meaningful)" section has the same arms A-D, E1-E3, exchange statistics and cost on `source = 'backfill'`, with no latency and no
  rule verdict. The trade story labels such reviews "retrospective review". Results: `data/year_test/dynamic_backfill/report.md` (a per-trade table) and `summary.json`.
- A past trade is a different sample from a live one (the entry already happened, the packet's `minutes_since_update` is 0, there is no latency to speak of), so it
  can inform how the reviewers behave, never the registered live decision.
