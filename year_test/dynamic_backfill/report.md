# Retrospective review of past trades (dynamic backfill)

Run 2026-10-27 22:01 NY, book **live**, prompt dyn-v1. These 10 trades had already closed; each was rebuilt as of its entry minute from OANDA candles and reviewed through the live path. The models were not told it was a past trade. Stored as `source = 'backfill'`: **not part of the live scorecard or its decision rule; latency is not meaningful.**

What was fetched from OANDA per trade: M1 bid/ask candles (price BA, complete only) for the 5 days before entry up to the minute before it, and H1 mid candles for the 60 days before entry (only hours closed by the entry minute are kept). Nothing at or after the entry minute was requested or used.

Cost estimate before the calls:

- claude claude-sonnet-5-5: up to 20 calls x typical tokens = ~48,980 in / ~8,000 out (output default; round 2: default) -> about $0.178 ($2.0/Mtok in, $10.0/Mtok out)
- openai gpt-6.1-sol: up to 20 calls x typical tokens = ~48,980 in / ~7,260 out (output avg of 10 past calls; round 2: default) -> about $0.171 ($2.0/Mtok in, $10.0/Mtok out)
- Estimated total: $0.348. An upper bound: round 2 only runs when both round-1 answers are valid.

Actual cost: $0.0926

## Per trade

| symbol | side | entry (NY) | actual R | Claude r1 | Claude r2 | OpenAI r1 | OpenAI r2 | exchange | cost USD |
|---|---|---|---|---|---|---|---|---|---|
| NDQ | SHORT | 2026-10-26 02:20 | +0.55 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0091 |
| NDQ | SHORT | 2026-10-25 23:30 | -1.14 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0098 |
| NDQ | SHORT | 2026-10-25 22:15 | +0.55 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0092 |
| XAUUSD | SHORT | 2026-10-25 20:45 | +0.55 | ABSTAIN | — | WAIT | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0098 |
| NDQ | SHORT | 2026-10-25 20:25 | +2.04 | ABSTAIN | — | WAIT | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0088 |
| XAUUSD | SHORT | 2026-10-23 14:30 | +0.55 | ABSTAIN | — | WAIT | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0091 |
| XAUUSD | SHORT | 2026-10-23 08:30 | +0.55 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0095 |
| XAUUSD | SHORT | 2026-10-23 04:25 | -1.02 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0089 |
| NDQ | SHORT | 2026-10-23 03:05 | -1.00 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0088 |
| NDQ | SHORT | 2026-10-23 02:00 | -1.01 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0096 |

## Past trades (retrospective, not counted toward the decision rule; latency not meaningful)

These trades had already closed when the reviewers saw them, rebuilt as of their entry minute from OANDA candles (the models were not told). **They are a separate sample: never pooled with the live scorecard above and not counted toward the decision rule.** Latency is not meaningful (calls were not made at the fill), so no latency or 30-second share is shown.

20 past trade(s) reviewed, 20 closed and scored.

| arm | candidates | entered | skipped (review / abstain / not reviewed) | total R | R per candidate | avoided losers | missed winners | API cost (USD / in R) | net R | latency p50 / p95 / max (s) | answered within 30 s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** every entry taken | 20 | 20 | 0 (0 / 0 / 0) | -2.92 | -0.146 | 0 (+0.00R) | 0 (+0.00R) | $0.000 / 0.000R | -2.92 | — | — |
| **B** OpenAI | 20 | 13 | 7 (7 / 0 / 0) | -3.56 | -0.178 | 3 (+3.06R) | 4 (+3.70R) | $0.184 / 0.001R | -3.56 | — | — |
| **C** Claude | 20 | 0 | 20 (0 / 20 / 0) | +0.00 | +0.000 | 10 (+10.23R) | 10 (+7.31R) | price not set | +0.00 | — | — |
| **D** both say ENTER | 20 | 0 | 20 (7 / 13 / 0) | +0.00 | +0.000 | 10 (+10.23R) | 10 (+7.31R) | $0.184 / 0.001R (20 call(s) without a price) | -0.00 | — | — |

Paired difference to A (skipping a trade removes its R; the API cost is subtracted):

| arm | reviewed closed trades | paired gross diff vs A (R per candidate) | net of API cost (R per candidate) | 95% range, net | decision rule |
|---|---|---|---|---|---|
| B OpenAI | 20 | -0.0320 | -0.0321 | needs >= 30 reviewed closed trades (has 20) | not counted |
| C Claude | 0 | +0.1459 | +0.1459 | needs >= 30 reviewed closed trades (has 0) | not counted |
| D both say ENTER | 0 | +0.1459 | +0.1459 | needs >= 30 reviewed closed trades (has 0) | not counted |

### Exchange (milestone 1b, prompt dyn-x1)

0 of 20 closed candidates were exchanged; **20 not exchanged** (E1/E2/E3 are not scored on those): skipped: round 1 not valid (claude: ABSTAIN) (20).

No exchanged candidates yet.

Everything the reviewers did (closed trades or not):

| provider | model | reviews | API calls | ENTER | WAIT | CANCEL | ABSTAIN | not reviewed | cost USD |
|---|---|---|---|---|---|---|---|---|---|
| claude | claude-sonnet-5-5 | 20 | 20 | 0 | 0 | 0 | 20 | 0 | 0.000 |
| openai | gpt-6.1-sol | 20 | 20 | 13 | 7 | 0 | 0 | 0 | 0.184 |

