# Journal vs OANDA — last 1 days

Matched positions 8 (0 by instrument + open time: trades from before the bot tagged its orders) · journal-only 0 · OANDA-only 0 · open/closed disagree 0 · untagged OANDA trades 0 · unit mismatches 0

Total on matched positions: journal **+2.49R**, OANDA **+2.40R** (OANDA = realizedPL + financing, converted from the account currency to USD at that day's rate, in each trade's own R — so the P&L difference holds financing and OANDA's conversion, not just fills).

| difference (R per position, OANDA − journal) | n | mean | median | worst | sum |
|---|---|---|---|---|---|
| P&L | 8 | -0.0110 | -0.0105 | -0.0200 | -0.088 |
| entry fill (+ = OANDA better) | 8 | +0.0000 | +0.0000 | -0.0000 | +0.000 |
| exit fill (+ = OANDA better) | 8 | +0.0000 | +0.0000 | -0.0000 | +0.000 |

## Target fills (market order after the level was touched; + = better than the level)

| kind | n | mean R | median R | worst R | total R |
|---|---|---|---|---|---|
| 1R partial | 3 | +0.0180 | +0.0039 | -0.0000 | +0.054 |
| full target | 4 | +0.0138 | +0.0025 | -0.0000 | +0.055 |
| all | 7 | +0.0156 | +0.0039 | -0.0000 | +0.109 |

A clearly negative mean here is what resting take-profit orders at the level would save (audit F5).

## Largest P&L differences

| id | symbol | strategy | opened | exit | journal R | OANDA R | diff R |
|---|---|---|---|---|---|---|---|
| 2a61ddfbe8 | XAUUSD | ict_ote:5m@v1 | 2026-10-22T13:30 | session_flat | 1.938 | 1.918 | -0.020 |
| 8c7472615e | NDQ | c10_afternoon | 2026-10-22T13:00 | target | 2.001 | 1.981 | -0.020 |
| 7e650cc353 | US30 | sr_rejection:15m@v1 | 2026-10-22T08:45 | stop | -1.017 | -1.029 | -0.012 |
| 29e0fbe405 | US30 | sr_rejection:5m@v1 | 2026-10-22T09:55 | stop | -1.007 | -1.018 | -0.011 |
| 8f32dcaa36 | US30 | sr_rejection:5m@v1 | 2026-10-22T21:20 | stop | -1.031 | -1.041 | -0.010 |
| 08f0ac06c3 | NDQ | sr_rejection:5m@v1 | 2026-10-22T08:40 | trail_stop | 1.046 | 1.037 | -0.009 |
| 923ea3f6c4 | US30 | sr_rejection:5m@v1 | 2026-10-22T09:00 | breakeven_plus_stop | 0.575 | 0.569 | -0.006 |
| 2c30b44435 | US30 | sr_rejection:15m@v1 | 2026-10-22T14:15 | session_flat | -0.013 | -0.013 | -0.000 |
