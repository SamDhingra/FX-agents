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

## Step 1 result and step 2 registration (Oct 28 2026)
Step 1 (explore) pointed to one consistent pattern: the first 30 minutes after a release tend to reverse over the next two hours
(pooled +0.89 ATR15 net, 10 of 12 release × instrument pairs). Registered as **news fade** (research/news_fade/), with Sam's choice
of a size-matched no-release control as a required gate; `./fx.sh newsfade test` judges it once on 2023-11-17 → 2026-10-01.
Backlog: indexes drifting up in the hour before CPI (+0.5 ATR15 vs −0.15 on no-release days) — too few CPI days for a test now.

## Outcome (Oct 28 2026): closed
- Registered news fade on 2023-11-17 → 2026-10-01: +0.16 ATR15 (−0.42..+0.77), halves +0.57 / −0.26, vs size-matched control
  +0.05 → fail. Its 4 × ATR15 stop fired on 40% of trades (sized from pre-release volatility — a design mistake).
- No-stop variant (addendum), judged once on 2016–2020: +0.10 ATR15 (−0.33..+0.55), −0.09 at 2× costs, vs control +0.51
  (−0.05..+1.08) → fail. Price-only fading of the first 30 minutes after these releases does not pay after costs.
- Backlog only: indexes drifting up in the hour before CPI (step 1; too few CPI days for a test now).
