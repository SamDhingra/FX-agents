# Hourly pick: before vs after taking Jev out (last 14 days, 627 logged hourly ratings)

Same logged hours, same strategy statistics, re-picked under each rule. Before = Jev 60% of the score, Jev's trade_ok gate, ×0.6 for strategies with fewer than 8 trades. Now = statistics only, small samples weighted by evidence. A pick needs a score ≥ 0.55; at most 1 per timeframe.

| instrument | hours rated | picks before | picks now |
|---|---|---|---|
| NDQ | 209 | 264 | 358 |
| US30 | 209 | 197 | 320 |
| XAUUSD | 209 | 194 | 217 |
| **all** | 627 | **655** | **895** |

## Hours with no pick, and why

| reason | before | now |
|---|---|---|
| Jev said don't trade this hour (trade_ok < 0.4) | 70 | 0 |
| no strategy scored ≥ 0.55 | 54 | 39 |

## Strategies picked (times)

| strategy | before | now |
|---|---|---|
| ict_ote:5m@v1 | 218 | 272 |
| smc_ifvg:15m@v1 | 165 | 233 |
| sr_rejection:5m@v1 | 179 | 164 |
| ict_ote:15m@v1 | 77 | 95 |
| stoic_sbs:5m@v1 | 15 | 120 |
| ict_fvg_sweep:5m@v1 | 1 | 11 |
