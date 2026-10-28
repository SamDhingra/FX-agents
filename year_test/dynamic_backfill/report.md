# Retrospective review of past trades (dynamic backfill)

Run 2026-10-27 22:25 NY, book **live**, prompt dyn-v1. These 20 trades had already closed; each was rebuilt as of its entry minute from OANDA candles and reviewed through the live path. The models were not told it was a past trade. Stored as `source = 'backfill'`: **not part of the live scorecard or its decision rule; latency is not meaningful.**

What was fetched from OANDA per trade: M1 bid/ask candles (price BA, complete only) for the 5 days before entry up to the minute before it, and H1 mid candles for the 60 days before entry (only hours closed by the entry minute are kept). Nothing at or after the entry minute was requested or used.

Cost estimate before the calls:

- claude claude-sonnet-5-5: up to 40 calls x typical tokens = ~98,301 in / ~16,000 out (output default; round 2: default) -> about $0.357 ($2.0/Mtok in, $10.0/Mtok out)
- openai gpt-6.1-sol: up to 20 calls x typical tokens = ~59,190 in / ~9,000 out (output avg of 20 past calls; round 2: default) -> about $0.208 ($2.0/Mtok in, $10.0/Mtok out)
- Estimated total: $0.565. An upper bound: round 2 only runs when both round-1 answers are valid.

Actual cost: $0.9530

## Per trade

| symbol | side | entry (NY) | actual R | Claude r1 | Claude r2 | OpenAI r1 | OpenAI r2 | exchange | cost USD |
|---|---|---|---|---|---|---|---|---|---|
| NDQ | LONG | 2026-10-27 13:00 | +0.72 | ENTER | ENTER | ENTER | ENTER | enter | 0.0454 |
| US30 | LONG | 2026-10-27 09:15 | -1.02 | WAIT | WAIT | WAIT | WAIT | wait | 0.0454 |
| US30 | LONG | 2026-10-27 08:40 | -1.02 | WAIT | WAIT | WAIT | WAIT | wait | 0.0471 |
| NDQ | LONG | 2026-10-26 13:00 | +0.20 | ENTER | ENTER | ENTER | ENTER | enter | 0.0441 |
| XAUUSD | SHORT | 2026-10-26 10:30 | -1.00 | ENTER | ENTER | ENTER | ENTER | enter | 0.0445 |
| NDQ | SHORT | 2026-10-26 10:00 | -1.00 | ENTER | ENTER | ENTER | ENTER | enter | 0.0481 |
| NDQ | SHORT | 2026-10-26 09:05 | +0.56 | ENTER | ENTER | WAIT | WAIT | cancel | 0.0491 |
| XAUUSD | SHORT | 2026-10-26 04:05 | -1.01 | WAIT | WAIT | WAIT | WAIT | wait | 0.0492 |
| NDQ | SHORT | 2026-10-26 03:45 | +1.05 | ENTER | ENTER | ENTER | ENTER | enter | 0.0471 |
| XAUUSD | SHORT | 2026-10-26 03:00 | -1.00 | ENTER | ENTER | ENTER | ENTER | enter | 0.0452 |
| NDQ | SHORT | 2026-10-26 02:20 | +0.55 | ENTER | ENTER | ENTER | ENTER | enter | 0.0450 |
| NDQ | SHORT | 2026-10-25 23:30 | -1.14 | ENTER | ENTER | ENTER | ENTER | enter | 0.0450 |
| NDQ | SHORT | 2026-10-25 22:15 | +0.55 | WAIT | WAIT | ENTER | ENTER | cancel | 0.0519 |
| XAUUSD | SHORT | 2026-10-25 20:45 | +0.55 | ENTER | ABSTAIN: invalid: reply cut off (max_tokens) | WAIT | WAIT | cancel | 0.0511 |
| NDQ | SHORT | 2026-10-25 20:25 | +2.04 | WAIT | WAIT | WAIT | WAIT | wait | 0.0515 |
| XAUUSD | SHORT | 2026-10-23 14:30 | +0.55 | ENTER | ENTER | WAIT | WAIT | cancel | 0.0477 |
| XAUUSD | SHORT | 2026-10-23 08:30 | +0.55 | ENTER | ENTER | ENTER | ENTER | enter | 0.0519 |
| XAUUSD | SHORT | 2026-10-23 04:25 | -1.02 | ENTER | ENTER | ENTER | ENTER | enter | 0.0491 |
| NDQ | SHORT | 2026-10-23 03:05 | -1.00 | ENTER | ENTER | ENTER | ENTER | enter | 0.0492 |
| NDQ | SHORT | 2026-10-23 02:00 | -1.01 | ENTER | ENTER | ENTER | ENTER | enter | 0.0454 |

## Past trades (retrospective, not counted toward the decision rule; latency not meaningful)

These trades had already closed when the reviewers saw them, rebuilt as of their entry minute from OANDA candles (the models were not told). **They are a separate sample: never pooled with the live scorecard above and not counted toward the decision rule.** Latency is not meaningful (calls were not made at the fill), so no latency or 30-second share is shown.

20 past trade(s) reviewed, 20 closed and scored.

| arm | candidates | entered | skipped (review / abstain / not reviewed) | total R | R per candidate | avoided losers | missed winners | API cost (USD / in R) | net R | latency p50 / p95 / max (s) | answered within 30 s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** every entry taken | 20 | 20 | 0 (0 / 0 / 0) | -2.92 | -0.146 | 0 (+0.00R) | 0 (+0.00R) | $0.000 / 0.000R | -2.92 | — | — |
| **B** OpenAI | 20 | 13 | 7 (7 / 0 / 0) | -3.56 | -0.178 | 3 (+3.06R) | 4 (+3.70R) | $0.184 / 0.001R | -3.56 | — | — |
| **C** Claude | 20 | 15 | 5 (5 / 0 / 0) | -2.46 | -0.123 | 3 (+3.06R) | 2 (+2.60R) | $0.242 / 0.002R | -2.46 | — | — |
| **D** both say ENTER | 20 | 12 | 8 (8 / 0 / 0) | -4.11 | -0.206 | 3 (+3.06R) | 5 (+4.25R) | $0.426 / 0.003R | -4.12 | — | — |

Paired difference to A (skipping a trade removes its R; the API cost is subtracted):

| arm | reviewed closed trades | paired gross diff vs A (R per candidate) | net of API cost (R per candidate) | 95% range, net | decision rule |
|---|---|---|---|---|---|
| B OpenAI | 20 | -0.0320 | -0.0321 | needs >= 30 reviewed closed trades (has 20) | not counted |
| C Claude | 20 | +0.0230 | +0.0230 | needs >= 30 reviewed closed trades (has 20) | not counted |
| D both say ENTER | 20 | -0.0596 | -0.0598 | needs >= 30 reviewed closed trades (has 20) | not counted |

### Exchange (milestone 1b, prompt dyn-x1)

20 of 20 closed candidates were exchanged; **0 not exchanged** (E1/E2/E3 are not scored on those).

Arms on the exchanged candidates only (A and D on the same subset, so E3 against D is a fair paired comparison). E arms are charged for the whole exchange: both reviewers' round 1 and round 2.

| arm | candidates | entered | skipped (review / abstain / not reviewed) | total R | R per candidate | avoided losers | missed winners | API cost (USD / in R) | net R | latency p50 / p95 / max (s) | answered within 30 s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** every entry taken | 20 | 20 | 0 (0 / 0 / 0) | -2.92 | -0.146 | 0 (+0.00R) | 0 (+0.00R) | $0.000 / 0.000R | -2.92 | — | — |
| **D** both say ENTER | 20 | 12 | 8 (8 / 0 / 0) | -4.11 | -0.206 | 3 (+3.06R) | 5 (+4.25R) | $0.426 / 0.003R | -4.12 | — | — |
| **E1** Claude, round 2 | 20 | 14 | 6 (5 / 1 / 0) | -3.00 | -0.150 | 3 (+3.06R) | 3 (+3.14R) | $0.953 / 0.006R | -3.01 | — | — |
| **E2** OpenAI, round 2 | 20 | 13 | 7 (7 / 0 / 0) | -3.56 | -0.178 | 3 (+3.06R) | 4 (+3.70R) | $0.953 / 0.006R | -3.57 | — | — |
| **E3** exchange decision rule | 20 | 12 | 8 (8 / 0 / 0) | -4.11 | -0.206 | 3 (+3.06R) | 5 (+4.25R) | $0.953 / 0.006R | -4.12 | — | — |

Paired difference to A on the exchanged subset (API cost subtracted):

| arm | reviewed closed trades | paired gross diff vs A (R per candidate) | net of API cost (R per candidate) | 95% range, net | decision rule |
|---|---|---|---|---|---|
| D both say ENTER | 20 | -0.0596 | -0.0598 | needs >= 30 reviewed closed trades (has 20) | not counted |
| E1 Claude, round 2 | 19 | -0.0042 | -0.0045 | needs >= 30 reviewed closed trades (has 19) | not counted |
| E2 OpenAI, round 2 | 20 | -0.0320 | -0.0324 | needs >= 30 reviewed closed trades (has 20) | not counted |
| E3 exchange decision rule | 19 | -0.0596 | -0.0600 | needs >= 30 reviewed closed trades (has 19) | not counted |

**E3 minus D** (net of each arm's own cost, R per candidate, 20 candidates): -0.0002 (needs >= 30 exchanged closed trades (has 20)); total -0.00R.

| reviewer | exchanged | changed its answer | toward ENTER | away from ENTER | other | R of round-1 answers on those trades | R of round-2 answers | gain |
|---|---|---|---|---|---|---|---|---|
| claude | 20 | 0 | 0 | 0 | 0 | +0.00 | +0.00 | +0.00 |
| openai | 20 | 0 | 0 | 0 | 0 | +0.00 | +0.00 | +0.00 |

(R of an answer = the trade's R if it said ENTER, else 0, as in arms B / C.)

Round-2 cost: $0.527 / 0.003R.

Everything the reviewers did (closed trades or not):

| provider | model | reviews | API calls | ENTER | WAIT | CANCEL | ABSTAIN | not reviewed | cost USD |
|---|---|---|---|---|---|---|---|---|---|
| openai | gpt-6.1-sol | 20 | 20 | 13 | 7 | 0 | 0 | 0 | 0.184 |
| claude | claude-sonnet-5-5 | 20 | 20 | 15 | 5 | 0 | 0 | 0 | 0.242 |

Round 2 (dyn-x1), everything the reviewers did:

| provider | model | reviews | API calls | ENTER | WAIT | CANCEL | ABSTAIN | not reviewed | cost USD |
|---|---|---|---|---|---|---|---|---|---|
| claude | claude-sonnet-5-5 | 20 | 20 | 14 | 5 | 0 | 1 | 0 | 0.313 |
| openai | gpt-6.1-sol | 20 | 20 | 13 | 7 | 0 | 0 | 0 | 0.214 |

Why claude did not answer (ABSTAIN / NOT_REVIEWED, both rounds):

| action | reason | count |
|---|---|---|
| ABSTAIN | invalid: reply cut off (max_tokens) | 1 |

