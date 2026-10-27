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
