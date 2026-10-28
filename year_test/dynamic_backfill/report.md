# Retrospective review of past trades (dynamic backfill)

Run 2026-10-27 21:25 NY, book **live**, prompt dyn-v1. These 10 trades had already closed; each was rebuilt as of its entry minute from OANDA candles and reviewed through the live path. The models were not told it was a past trade. Stored as `source = 'backfill'`: **not part of the live scorecard or its decision rule; latency is not meaningful.**

What was fetched from OANDA per trade: M1 bid/ask candles (price BA, complete only) for the 5 days before entry up to the minute before it, and H1 mid candles for the 60 days before entry (only hours closed by the entry minute are kept). Nothing at or after the entry minute was requested or used.

Cost estimate before the calls:

- claude claude-sonnet-5-5: up to 20 calls x typical tokens = ~49,320 in / ~8,000 out (output default; round 2: default) -> about $0.179 ($2.0/Mtok in, $10.0/Mtok out)
- openai gpt-6.1-sol: up to 20 calls x typical tokens = ~49,320 in / ~8,000 out (output default; round 2: default) -> about $0.179 ($2.0/Mtok in, $10.0/Mtok out)
- Estimated total: $0.357. An upper bound: round 2 only runs when both round-1 answers are valid.

Actual cost: $0.0910

## Per trade

| symbol | side | entry (NY) | actual R | Claude r1 | Claude r2 | OpenAI r1 | OpenAI r2 | exchange | cost USD |
|---|---|---|---|---|---|---|---|---|---|
| NDQ | LONG | 2026-10-27 13:00 | +0.72 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0095 |
| US30 | LONG | 2026-10-27 09:15 | -1.02 | ABSTAIN | — | WAIT | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0097 |
| US30 | LONG | 2026-10-27 08:40 | -1.02 | ABSTAIN | — | WAIT | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0081 |
| NDQ | LONG | 2026-10-26 13:00 | +0.20 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0089 |
| XAUUSD | SHORT | 2026-10-26 10:30 | -1.00 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0087 |
| NDQ | SHORT | 2026-10-26 10:00 | -1.00 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0089 |
| NDQ | SHORT | 2026-10-26 09:05 | +0.56 | ABSTAIN | — | WAIT | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0096 |
| XAUUSD | SHORT | 2026-10-26 04:05 | -1.01 | ABSTAIN | — | WAIT | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0091 |
| NDQ | SHORT | 2026-10-26 03:45 | +1.05 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0091 |
| XAUUSD | SHORT | 2026-10-26 03:00 | -1.00 | ABSTAIN | — | ENTER | — | skipped: round 1 not valid (claude: ABSTAIN) | 0.0094 |

## Past trades (retrospective, not counted toward the decision rule; latency not meaningful)

These trades had already closed when the reviewers saw them, rebuilt as of their entry minute from OANDA candles (the models were not told). **They are a separate sample: never pooled with the live scorecard above and not counted toward the decision rule.** Latency is not meaningful (calls were not made at the fill), so no latency or 30-second share is shown.

10 past trade(s) reviewed, 10 closed and scored.

| arm | candidates | entered | skipped (review / abstain / not reviewed) | total R | R per candidate | avoided losers | missed winners | API cost (USD / in R) | net R | latency p50 / p95 / max (s) | answered within 30 s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** every entry taken | 10 | 10 | 0 (0 / 0 / 0) | -3.54 | -0.354 | 0 (+0.00R) | 0 (+0.00R) | $0.000 / 0.000R | -3.54 | — | — |
| **B** OpenAI | 10 | 6 | 4 (4 / 0 / 0) | -1.04 | -0.104 | 3 (+3.06R) | 1 (+0.56R) | $0.091 / 0.001R | -1.04 | — | — |
| **C** Claude | 10 | 0 | 10 (0 / 10 / 0) | +0.00 | +0.000 | 6 (+6.06R) | 4 (+2.52R) | price not set | +0.00 | — | — |
| **D** both say ENTER | 10 | 0 | 10 (4 / 6 / 0) | +0.00 | +0.000 | 6 (+6.06R) | 4 (+2.52R) | $0.091 / 0.001R (10 call(s) without a price) | -0.00 | — | — |

Paired difference to A (skipping a trade removes its R; the API cost is subtracted):

| arm | reviewed closed trades | paired gross diff vs A (R per candidate) | net of API cost (R per candidate) | 95% range, net | decision rule |
|---|---|---|---|---|---|
| B OpenAI | 10 | +0.2500 | +0.2499 | needs >= 30 reviewed closed trades (has 10) | not counted |
| C Claude | 0 | +0.3539 | +0.3539 | needs >= 30 reviewed closed trades (has 0) | not counted |
| D both say ENTER | 0 | +0.3539 | +0.3538 | needs >= 30 reviewed closed trades (has 0) | not counted |

### Exchange (milestone 1b, prompt dyn-x1)

0 of 10 closed candidates were exchanged; **10 not exchanged** (E1/E2/E3 are not scored on those): skipped: round 1 not valid (claude: ABSTAIN) (10).

No exchanged candidates yet.

Everything the reviewers did (closed trades or not):

| provider | model | reviews | API calls | ENTER | WAIT | CANCEL | ABSTAIN | not reviewed | cost USD |
|---|---|---|---|---|---|---|---|---|---|
| claude | claude-sonnet-5-5 | 10 | 10 | 0 | 0 | 0 | 10 | 0 | 0.000 |
| openai | gpt-6.1-sol | 10 | 10 | 6 | 4 | 0 | 0 | 0 | 0.091 |

