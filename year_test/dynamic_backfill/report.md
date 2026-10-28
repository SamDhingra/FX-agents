# Retrospective review of past trades (dynamic backfill)

Run 2026-10-28 12:34 NY, book **live**, prompt dyn-v1. These 20 trades had already closed; each was rebuilt as of its entry minute from OANDA candles and reviewed through the live path. The models were not told it was a past trade. Stored as `source = 'backfill'`: **not part of the live scorecard or its decision rule; latency is not meaningful.**

What was fetched from OANDA per trade: M1 bid/ask candles (price BA, complete only) for the 5 days before entry up to the minute before it, and H1 mid candles for the 60 days before entry (only hours closed by the entry minute are kept). Nothing at or after the entry minute was requested or used.

Cost estimate before the calls:

- claude claude-sonnet-5-5: up to 40 calls x typical tokens = ~100,574 in / ~19,340 out (output avg of 22 past calls; round 2: avg of 22 past calls) -> about $0.395 ($2.0/Mtok in, $10.0/Mtok out)
- openai gpt-6.1-sol: up to 40 calls x typical tokens = ~100,574 in / ~11,660 out (output avg of 22 past calls; round 2: avg of 22 past calls) -> about $0.318 ($2.0/Mtok in, $10.0/Mtok out)
- Estimated total: $0.712. An upper bound: round 2 only runs when both round-1 answers are valid.

Actual cost: $0.4273

## Per trade

| symbol | side | entry (NY) | actual R | Claude r1 | Claude r2 | OpenAI r1 | OpenAI r2 | exchange | cost USD |
|---|---|---|---|---|---|---|---|---|---|
| NDQ | LONG | 2026-10-27 13:00 | +0.72 | ENTER | — | ENTER | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0203 |
| US30 | LONG | 2026-10-27 09:15 | -1.02 | WAIT | — | WAIT | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0205 |
| US30 | LONG | 2026-10-27 08:40 | -1.02 | WAIT | — | WAIT | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0254 |
| NDQ | LONG | 2026-10-26 13:00 | +0.20 | ENTER | — | ENTER | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0198 |
| XAUUSD | SHORT | 2026-10-26 10:30 | -1.00 | ENTER | — | ENTER | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0200 |
| NDQ | SHORT | 2026-10-26 10:00 | -1.00 | ENTER | — | ENTER | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0258 |
| NDQ | SHORT | 2026-10-26 09:05 | +0.56 | ENTER | — | WAIT | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0208 |
| XAUUSD | SHORT | 2026-10-26 04:05 | -1.01 | WAIT | — | WAIT | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0247 |
| NDQ | SHORT | 2026-10-26 03:45 | +1.05 | ENTER | — | ENTER | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0200 |
| XAUUSD | SHORT | 2026-10-26 03:00 | -1.00 | WAIT | — | ENTER | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0204 |
| NDQ | SHORT | 2026-10-26 02:20 | +0.55 | ENTER | — | ENTER | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0195 |
| NDQ | SHORT | 2026-10-25 23:30 | -1.14 | ENTER | — | ENTER | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0201 |
| NDQ | SHORT | 2026-10-25 22:15 | +0.55 | WAIT | — | ENTER | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0203 |
| XAUUSD | SHORT | 2026-10-25 20:45 | +0.55 | ENTER | — | WAIT | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0200 |
| NDQ | SHORT | 2026-10-25 20:25 | +2.04 | WAIT | — | WAIT | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0197 |
| XAUUSD | SHORT | 2026-10-23 14:30 | +0.55 | ENTER | — | WAIT | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0246 |
| XAUUSD | SHORT | 2026-10-23 08:30 | +0.55 | WAIT | — | WAIT | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0203 |
| XAUUSD | SHORT | 2026-10-23 04:25 | -1.02 | ENTER | — | ENTER | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0243 |
| NDQ | SHORT | 2026-10-23 03:05 | -1.00 | ENTER | — | ENTER | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0203 |
| NDQ | SHORT | 2026-10-23 02:00 | -1.01 | ENTER | — | ENTER | — | skipped: exchange switched off (dynamic.exchange: false) | 0.0205 |

## Past trades (retrospective, not counted toward the decision rule; latency not meaningful)

These trades had already closed when the reviewers saw them, rebuilt as of their entry minute from OANDA candles (the models were not told). **They are a separate sample: never pooled with the live scorecard above and not counted toward the decision rule.** Latency is not meaningful (calls were not made at the fill), so no latency or 30-second share is shown.

20 past trade(s) reviewed, 20 closed and scored.

| arm | candidates | entered | skipped (review / abstain / not reviewed) | total R | R per candidate | avoided losers | missed winners | API cost (USD / in R) | net R | latency p50 / p95 / max (s) | answered within 30 s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** every entry taken | 20 | 20 | 0 (0 / 0 / 0) | -2.92 | -0.146 | 0 (+0.00R) | 0 (+0.00R) | $0.000 / 0.000R | -2.92 | — | — |
| **B** OpenAI | 20 | 12 | 8 (8 / 0 / 0) | -4.11 | -0.205 | 3 (+3.06R) | 5 (+4.25R) | $0.179 / 0.001R | -4.11 | — | — |
| **C** Claude | 20 | 13 | 7 (7 / 0 / 0) | -2.01 | -0.100 | 4 (+4.06R) | 3 (+3.15R) | $0.248 / 0.002R | -2.01 | — | — |
| **D** both say ENTER | 20 | 10 | 10 (10 / 0 / 0) | -3.66 | -0.183 | 4 (+4.06R) | 6 (+4.80R) | $0.427 / 0.003R | -3.67 | — | — |

Paired difference to A (skipping a trade removes its R; the API cost is subtracted):

| arm | reviewed closed trades | paired gross diff vs A (R per candidate) | net of API cost (R per candidate) | 95% range, net | decision rule |
|---|---|---|---|---|---|
| B OpenAI | 20 | -0.0596 | -0.0597 | needs >= 30 reviewed closed trades (has 20) | not counted |
| C Claude | 20 | +0.0455 | +0.0455 | needs >= 30 reviewed closed trades (has 20) | not counted |
| D both say ENTER | 20 | -0.0372 | -0.0373 | needs >= 30 reviewed closed trades (has 20) | not counted |

### Exchange (milestone 1b, prompt dyn-x1)

0 of 20 closed candidates were exchanged; **20 not exchanged** (E1/E2/E3 are not scored on those): skipped: exchange switched off (dynamic.exchange: false) (20).

No exchanged candidates yet.

Everything the reviewers did (closed trades or not):

| provider | model | reviews | API calls | ENTER | WAIT | CANCEL | ABSTAIN | not reviewed | cost USD |
|---|---|---|---|---|---|---|---|---|---|
| claude | claude-sonnet-5-5 | 20 | 20 | 13 | 7 | 0 | 0 | 0 | 0.248 |
| openai | gpt-6.1-sol | 20 | 20 | 12 | 8 | 0 | 0 | 0 | 0.179 |

