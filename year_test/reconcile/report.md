# Journal vs OANDA — last 30 days

Matched positions 73 (26 by instrument + open time: trades from before the bot tagged its orders) · journal-only {s['journal_only']} · OANDA-only {s['broker_only']} · open/closed disagree 3 · untagged OANDA trades 1 · unit mismatches 2

Total on matched positions: journal **+6.87R**, OANDA **+16.83R** (OANDA = realizedPL + financing, converted from the account currency to USD at that day's rate, in each trade's own R — so the P&L difference holds financing and OANDA's conversion, not just fills).

| difference (R per position, OANDA − journal) | n | mean | median | worst | sum |
|---|---|---|---|---|---|
| P&L | 73 | +0.1365 | -0.0100 | -0.2600 | +9.963 |
| entry fill (+ = OANDA better) | 73 | +0.0148 | +0.0000 | -0.0000 | +1.078 |
| exit fill (+ = OANDA better) | 73 | -0.0496 | -0.4560 | -3.8390 | -3.623 |

## Target fills (market order after the level was touched; + = better than the level)

| kind | n | mean R | median R | worst R | total R |
|---|---|---|---|---|---|
| 1R partial | 34 | -0.0486 | -0.0190 | -0.7148 | -1.654 |
| full target | 0 | – | – | – | – |
| all | 34 | -0.0486 | -0.0190 | -0.7148 | -1.654 |

A clearly negative mean here is what resting take-profit orders at the level would save (audit F5).

## Journal trades with no OANDA trade (1)

| id | symbol | strategy | status | opened |
|---|---|---|---|---|
| cf8f0d0885 | XAUUSD | smc_ifvg:5m@v1 | open | 2026-10-08T10:55:06.731648-04:00 |

## Open at one side, closed at the other (3)

| id | symbol | journal | oanda |
|---|---|---|---|
| 65d63a10a7 | XAUUSD | open | CLOSED |
| 449d0a812b | NDQ | open | CLOSED |
| 9abec21d22 | XAUUSD | open | CLOSED |

## OANDA trades without the bot's tag (1)

| instrument | opened | state |
|---|---|---|
| NAS100_USD | 2026-10-05T08:17:04.779278752Z | CLOSED |

## Largest P&L differences

| id | symbol | strategy | opened | exit | journal R | OANDA R | diff R |
|---|---|---|---|---|---|---|---|
| 9acd6396c9 | XAUUSD | orphan:unmanaged | 2026-10-08T10:55 | orphan_close | 9.089 | 19.927 | +10.838 |
| 8905837204 | NDQ | smc_ifvg:5m@v1 | 2026-10-05T03:55 | trail_stop | 0.471 | 1.022 | +0.551 |
| 68bd9f185a | XAUUSD | sr_rejection:15m@v1 | 2026-10-06T20:00 | breakeven_plus_stop | 0.839 | 0.579 | -0.260 |
| 05edb2bef0 | US30 | sr_rejection:5m@v1 | 2026-10-06T21:20 | breakeven_plus_stop | 0.751 | 0.52 | -0.231 |
| 8688df3637 | US30 | sr_rejection:5m@v1 | 2026-10-06T23:05 | breakeven_plus_stop | 0.74 | 0.511 | -0.229 |
| e9c552c4d3 | NDQ | sr_rejection:5m@v1 | 2026-10-06T23:25 | breakeven_plus_stop | 0.261 | 0.199 | -0.062 |
| b1c53ffd78 | US30 | sr_rejection:5m@v1 | 2026-10-18T21:40 | trail_stop | 3.839 | 3.803 | -0.036 |
| 643a992163 | US30 | sr_rejection:5m@v1 | 2026-10-14T03:55 | trail_stop | 2.49 | 2.46 | -0.030 |
| 84db768b4c | XAUUSD | smc_ifvg:5m@v1 | 2026-10-06T09:25 | trail_stop | 1.122 | 1.103 | -0.019 |
| de0bdc47f0 | US30 | sr_rejection:5m@v1 | 2026-10-20T09:45 | trail_stop | 1.522 | 1.506 | -0.016 |
| 7a2291e93a | XAUUSD | sr_rejection:15m@v1 | 2026-10-06T03:30 | stop | -1.016 | -1.031 | -0.015 |
| 95c752ed0d | US30 | sr_rejection:5m@v1 | 2026-10-21T11:05 | trail_stop | 1.566 | 1.552 | -0.014 |
| a7226d51cb | NDQ | sr_rejection:5m@v1 | 2026-10-15T21:00 | stop | -1.007 | -1.021 | -0.014 |
| 2b1f0e6567 | XAUUSD | smc_ifvg:15m@v1 | 2026-10-12T21:30 | stop | -1.005 | -1.019 | -0.014 |
| cd013c6d27 | XAUUSD | sr_rejection:15m@v1 | 2026-10-05T20:45 | stop | -1.006 | -1.02 | -0.014 |
