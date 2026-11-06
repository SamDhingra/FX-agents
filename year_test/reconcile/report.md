# Journal vs OANDA — last 14 days

Matched positions 37 (0 by instrument + open time: trades from before the bot tagged its orders) · journal-only 0 · OANDA-only 1 · open/closed disagree 0 · untagged OANDA trades 0 · unit mismatches 0

Total on matched positions: journal **-2.64R**, OANDA **-2.96R** (OANDA = realizedPL + financing, converted from the account currency to USD at that day's rate, in each trade's own R — so the P&L difference holds financing and OANDA's conversion, not just fills).

| difference (R per position, OANDA − journal) | n | mean | median | worst | sum |
|---|---|---|---|---|---|
| P&L | 37 | -0.0087 | -0.0080 | -0.0220 | -0.322 |
| entry fill (+ = OANDA better) | 37 | +0.0000 | +0.0000 | -0.0000 | +0.000 |
| exit fill (+ = OANDA better) | 37 | +0.0000 | +0.0000 | -0.0000 | +0.000 |

## Target fills (market order after the level was touched; + = better than the level)

| kind | n | mean R | median R | worst R | total R |
|---|---|---|---|---|---|
| 1R partial | 15 | +0.0496 | +0.0088 | -0.0000 | +0.743 |
| full target | 15 | +0.0496 | +0.0088 | -0.0000 | +0.743 |
| all | 30 | +0.0496 | +0.0088 | -0.0000 | +1.487 |

A clearly negative mean here is what resting take-profit orders at the level would save (audit F5).

## OANDA trades the journal doesn't have (1)

| id | instrument | legs | open_at_oanda |
|---|---|---|---|
| f2fe057e5c | XAU_USD | 1 | False |

## Largest P&L differences

| id | symbol | strategy | opened | exit | journal R | OANDA R | diff R |
|---|---|---|---|---|---|---|---|
| 47d0866c6f | NDQ | c10_afternoon | 2026-10-30T13:00 | stop | 2.001 | 1.979 | -0.022 |
| faa7972347 | NDQ | sr_rejection:5m@v1 | 2026-10-25T20:25 | trail_stop | 2.044 | 2.022 | -0.022 |
| ad6e6ce5bf | NDQ | sr_rejection:15m@v1 | 2026-10-26T10:00 | stop | -1.0 | -1.013 | -0.013 |
| d806b7fffd | XAUUSD | ict_ote:15m@v1 | 2026-10-26T10:30 | stop | -1.001 | -1.013 | -0.012 |
| e2c17325c6 | NDQ | ict_ote:5m@v1 | 2026-11-03T13:30 | trail_stop | 1.038 | 1.027 | -0.011 |
| 301afeade0 | XAUUSD | ict_ote:5m@v1 | 2026-10-26T04:05 | stop | -1.015 | -1.026 | -0.011 |
| 4f85e7994c | XAUUSD | sr_rejection:15m@v1 | 2026-10-26T03:00 | stop | -1.001 | -1.012 | -0.011 |
| 1802010927 | NDQ | sr_rejection:15m@v1 | 2026-10-25T23:30 | stop | -1.141 | -1.152 | -0.011 |
| 09095000dd | NDQ | smc_ifvg:15m@v1 | 2026-11-04T21:30 | max_hold | 0.66 | 0.65 | -0.010 |
| d6d99d5896 | XAUUSD | ict_ote:5m@v1 | 2026-10-29T13:30 | trail_stop | 0.963 | 0.953 | -0.010 |
| 5fcbb0ae2b | NDQ | smc_ifvg:15m@v1 | 2026-11-06T11:15 | stop | -1.025 | -1.034 | -0.009 |
| 2f3d7ead99 | NDQ | sr_rejection:5m@v1 | 2026-11-05T22:35 | breakeven_plus_stop | 0.566 | 0.557 | -0.009 |
| cd893fef48 | US30 | sr_rejection:5m@v1 | 2026-11-05T15:20 | stop | -1.006 | -1.015 | -0.009 |
| 2a52753f6e | XAUUSD | ict_ote:5m@v1 | 2026-10-30T04:10 | stop | -1.007 | -1.016 | -0.009 |
| 43e1ef8f76 | NDQ | ict_ote:15m@v1 | 2026-10-30T02:30 | trail_stop | 0.825 | 0.816 | -0.009 |
