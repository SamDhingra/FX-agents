# News trading study (started Oct 28 2026)

Question (Sam): the bot takes no entries 30 min before / after tier-1 USD news. Is there a repeatable pattern before or after the
releases — by release type and instrument — that would be a niche edge?

## Data and limits
- Releases: `fxagents/usd_calendar.py` — FOMC (14:00), CPI, NFP, PPI (08:30 NY), official dates 2016 – Oct 2026, ~44 a year.
  Other releases the live feed treats as tier 1 (PCE, GDP, Fed Chair) are not in the historical calendar.
- Prices: OANDA M1 bid/ask exports (XAUUSD, NDQ, US30), with the real spread of every minute — release minutes are expensive.
- No released numbers / forecasts (the surprise): not in the calendar, and the live feed has no real-time actual, so a rule can
  only use prices (e.g. the direction of the first minutes after the release, which is the market's own read of the surprise).
- Small samples: ~8 FOMC and ~12 of each other type a year per instrument.

## Plan (fixed before any number was seen)
1. **Explore** (`./fx.sh newsstudy`): descriptive event study on 2021-01-01 → 2023-11-17 only; the M1 data is cut at the split
   before anything runs. Volatility and spread around the release, pre-release drift, pre-move vs reaction, continuation vs
   fade after the first 5 / 15 / 30 minutes, against no-release days at the same clock time.
2. **Register** at most a few fixed rules from step 1, then judge them once on 2023-11-17 → 2026-10-01 (usual gates: ≥ 100
   trades, 95% range above 0, both halves, 2× costs, beat a control).
3. **Confirm** a passer once on 2016–2020. No trading change before the Nov 5 review; the blackout stays as it is meanwhile.
