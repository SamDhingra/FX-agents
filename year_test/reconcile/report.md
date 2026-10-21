# Journal vs OANDA — last 30 days

Matched positions 47 · journal-only 30 · OANDA-only 0 · open/closed disagree 0 · untagged OANDA trades 30 · unit mismatches 0

Total on matched positions: journal **+2.59R**, OANDA **+2.93R** (OANDA = realizedPL + financing, in each trade's own R).

| difference (R per position, OANDA − journal) | n | mean | median | worst | sum |
|---|---|---|---|---|---|
| P&L | 47 | +0.0074 | +0.0700 | -0.4610 | +0.346 |
| entry fill (+ = OANDA better) | 47 | +0.0000 | +0.0000 | +0.0000 | +0.000 |
| exit fill (+ = OANDA better) | 47 | -0.0590 | +0.0000 | -2.7230 | -2.773 |

## Target fills (market order after the level was touched; + = better than the level)

| kind | n | mean R | median R | worst R | total R |
|---|---|---|---|---|---|
| 1R partial | 34 | -0.0486 | -0.0190 | -0.7148 | -1.654 |
| full target | 0 | – | – | – | – |
| all | 34 | -0.0486 | -0.0190 | -0.7148 | -1.654 |

A clearly negative mean here is what resting take-profit orders at the level would save (audit F5).

## Journal trades with no OANDA trade (30)

| id | symbol | strategy | status | opened |
|---|---|---|---|---|
| 12b3f2d657 | US30 | smc_ifvg:5m@v1 | closed | 2026-10-05T02:35:05.043748-04:00 |
| 9e3968121e | US30 | smc_ifvg:5m@v1 | closed | 2026-10-05T03:45:04.641651-04:00 |
| 8905837204 | NDQ | smc_ifvg:5m@v1 | closed | 2026-10-05T03:55:04.919974-04:00 |
| f4e4c35af9 | XAUUSD | sr_rejection:15m@v1 | closed | 2026-10-05T08:45:03.840905-04:00 |
| a789dc50ea | XAUUSD | smc_ifvg:5m@v1 | closed | 2026-10-05T14:20:05.290657-04:00 |
| cd013c6d27 | XAUUSD | sr_rejection:15m@v1 | closed | 2026-10-05T20:45:02.902581-04:00 |
| b5792763b7 | XAUUSD | smc_ifvg:5m@v1 | closed | 2026-10-05T21:35:02.462678-04:00 |
| 9abec21d22 | XAUUSD | smc_ifvg:5m@v1 | open | 2026-10-05T22:55:04.198430-04:00 |
| 7a2291e93a | XAUUSD | sr_rejection:15m@v1 | closed | 2026-10-06T03:30:04.418071-04:00 |
| 3625e0e92f | NDQ | ict_ote:5m@v1 | closed | 2026-10-06T04:30:06.272337-04:00 |
| 84db768b4c | XAUUSD | smc_ifvg:5m@v1 | closed | 2026-10-06T09:25:02.611884-04:00 |
| cccbe3918f | NDQ | ict_ote:5m@v1 | closed | 2026-10-06T10:30:05.627757-04:00 |
| 5938e1c4a7 | XAUUSD | smc_ifvg:5m@v1 | closed | 2026-10-06T11:05:03.169582-04:00 |
| 27ffded103 | XAUUSD | sr_rejection:15m@v1 | closed | 2026-10-06T14:00:07.031546-04:00 |
| 449d0a812b | NDQ | ict_ote:5m@v1 | open | 2026-10-06T14:40:03.949905-04:00 |
| 68bd9f185a | XAUUSD | sr_rejection:15m@v1 | closed | 2026-10-06T20:00:04.094718-04:00 |
| eb2000bea1 | US30 | sr_rejection:5m@v1 | closed | 2026-10-06T20:50:07.732986-04:00 |
| 05edb2bef0 | US30 | sr_rejection:5m@v1 | closed | 2026-10-06T21:20:10.161999-04:00 |
| 3cb82dd484 | NDQ | sr_rejection:5m@v1 | closed | 2026-10-06T23:00:04.109613-04:00 |
| 8688df3637 | US30 | sr_rejection:5m@v1 | closed | 2026-10-06T23:05:04.479619-04:00 |
| e9c552c4d3 | NDQ | sr_rejection:5m@v1 | closed | 2026-10-06T23:25:05.974226-04:00 |
| d5cf992877 | XAUUSD | smc_ifvg:5m@v1 | closed | 2026-10-06T23:40:04.349682-04:00 |
| 4d149f9608 | XAUUSD | smc_ifvg:5m@v1 | closed | 2026-10-07T02:00:03.941268-04:00 |
| 79b0c6467b | US30 | sr_rejection:15m@v1 | closed | 2026-10-07T09:30:04.415519-04:00 |
| 5fbf5e41d2 | NDQ | sr_rejection:15m@v1 | closed | 2026-10-07T10:00:05.736231-04:00 |
| 36436ce150 | XAUUSD | smc_ifvg:5m@v1 | closed | 2026-10-07T23:05:05.374958-04:00 |
| 65d63a10a7 | XAUUSD | smc_ifvg:5m@v1 | open | 2026-10-08T03:40:06.207021-04:00 |
| dd022e4bb5 | XAUUSD | ict_ote:15m@v1 | closed | 2026-10-08T08:45:05.758931-04:00 |
| cf8f0d0885 | XAUUSD | smc_ifvg:5m@v1 | open | 2026-10-08T10:55:06.731648-04:00 |
| 9acd6396c9 | XAUUSD | orphan:unmanaged | closed | 2026-10-08T10:55:07.003163644-04:00 |

## OANDA trades without the bot's tag (30)

| instrument | opened | state |
|---|---|---|
| XAU_USD | 2026-10-08T14:55:07.003163644Z | CLOSED |
| XAU_USD | 2026-10-08T12:45:06.052729226Z | CLOSED |
| XAU_USD | 2026-10-08T07:40:06.441783917Z | CLOSED |
| XAU_USD | 2026-10-08T03:05:05.596062732Z | CLOSED |
| NAS100_USD | 2026-10-07T14:00:06.278815818Z | CLOSED |
| US30_USD | 2026-10-07T13:30:04.845071551Z | CLOSED |
| XAU_USD | 2026-10-07T06:00:04.301688525Z | CLOSED |
| XAU_USD | 2026-10-07T03:40:04.729319365Z | CLOSED |
| NAS100_USD | 2026-10-07T03:25:06.205985166Z | CLOSED |
| US30_USD | 2026-10-07T03:05:04.773617992Z | CLOSED |
| NAS100_USD | 2026-10-07T03:00:04.568038916Z | CLOSED |
| US30_USD | 2026-10-07T01:20:10.427326043Z | CLOSED |
| US30_USD | 2026-10-07T00:50:08.043558663Z | CLOSED |
| XAU_USD | 2026-10-07T00:00:04.538291952Z | CLOSED |
| NAS100_USD | 2026-10-06T18:40:04.315043701Z | CLOSED |
| XAU_USD | 2026-10-06T18:00:07.654133224Z | CLOSED |
| XAU_USD | 2026-10-06T15:05:03.886520417Z | CLOSED |
| NAS100_USD | 2026-10-06T14:30:05.860943571Z | CLOSED |
| XAU_USD | 2026-10-06T13:25:03.077811211Z | CLOSED |
| NAS100_USD | 2026-10-06T08:30:06.484826260Z | CLOSED |
| XAU_USD | 2026-10-06T07:30:04.697402778Z | CLOSED |
| XAU_USD | 2026-10-06T02:55:04.484163809Z | CLOSED |
| XAU_USD | 2026-10-06T01:35:02.846431393Z | CLOSED |
| XAU_USD | 2026-10-06T00:45:03.435795172Z | CLOSED |
| XAU_USD | 2026-10-05T18:20:05.581019735Z | CLOSED |
| XAU_USD | 2026-10-05T12:45:04.158436604Z | CLOSED |
| NAS100_USD | 2026-10-05T08:17:04.779278752Z | CLOSED |
| NAS100_USD | 2026-10-05T07:55:05.102236359Z | CLOSED |
| US30_USD | 2026-10-05T07:45:04.814744176Z | CLOSED |
| US30_USD | 2026-10-05T06:35:05.278680003Z | CLOSED |

## Largest P&L differences

| id | symbol | strategy | opened | exit | journal R | OANDA R | diff R |
|---|---|---|---|---|---|---|---|
| b1c53ffd78 | US30 | sr_rejection:5m@v1 | 2026-10-18T21:40 | trail_stop | 3.839 | 5.367 | +1.528 |
| 643a992163 | US30 | sr_rejection:5m@v1 | 2026-10-14T03:55 | trail_stop | 2.49 | 3.502 | +1.012 |
| 492b1a1ea9 | US30 | sr_rejection:5m@v1 | 2026-10-09T11:05 | trail_stop | 1.582 | 2.237 | +0.655 |
| a2b33b0064 | US30 | ict_ote:15m@v1 | 2026-10-16T02:15 | trail_stop | 1.562 | 2.19 | +0.628 |
| 95c752ed0d | US30 | sr_rejection:5m@v1 | 2026-10-21T11:05 | trail_stop | 1.566 | 2.181 | +0.615 |
| de0bdc47f0 | US30 | sr_rejection:5m@v1 | 2026-10-20T09:45 | trail_stop | 1.522 | 2.117 | +0.595 |
| 966374769e | NDQ | smc_ifvg:5m@v1 | 2026-10-16T09:00 | trail_stop | 1.342 | 1.881 | +0.539 |
| 309cbd718c | NDQ | ict_ote:5m@v1 | 2026-10-09T04:25 | trail_stop | 1.258 | 1.777 | +0.519 |
| 79eb71c355 | US30 | sr_rejection:5m@v1 | 2026-10-12T13:45 | stop | -1.042 | -1.503 | -0.461 |
| 6e5a359a9b | XAUUSD | smc_ifvg:5m@v1 | 2026-10-12T10:35 | stop | -1.044 | -1.505 | -0.461 |
| e247f6a3e9 | NDQ | sr_rejection:5m@v1 | 2026-10-20T15:00 | trail_stop | 1.173 | 1.633 | +0.460 |
| 07c501687c | NDQ | ict_ote:5m@v1 | 2026-10-19T14:45 | stop | -1.074 | -1.53 | -0.456 |
| 1b47d6bf8d | US30 | sr_rejection:5m@v1 | 2026-10-12T15:05 | stop | -1.022 | -1.474 | -0.452 |
| 808bce71d7 | XAUUSD | smc_ifvg:5m@v1 | 2026-10-12T10:25 | stop | -1.026 | -1.478 | -0.452 |
| f82e88aaee | US30 | smc_ifvg:5m@v1 | 2026-10-12T03:10 | stop | -1.024 | -1.474 | -0.450 |
