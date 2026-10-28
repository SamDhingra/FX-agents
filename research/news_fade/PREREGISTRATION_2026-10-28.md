# News fade — pre-registration (Oct 28 2026, before the test data is read)

Source: the news event study, step 1 (`./fx.sh newsstudy`, 2021-01-01 → 2023-11-17 only): pooled over all releases and
instruments, fading the T−1 → T+30 move from T+30 and holding 120 minutes averaged +0.89 ATR15 net of the spread
(+0.14..+1.63), the reversal appearing in 10 of 12 release × instrument pairs. Chosen with Sam, Oct 28 2026.

## Rule (fixed)
- **Releases:** FOMC (14:00), CPI, NFP, PPI (08:30 NY) from `fxagents/usd_calendar.py`. **Instruments:** XAUUSD, NDQ, US30
  — all of them, gold-after-NFP included (it went the other way in step 1; excluding it now would be fitting).
- **Units:** ATR15 = mean true range of the 20 M15 candles closed by T−60 (as in step 1).
- **Direction:** against the move from T−1 to T+30 (mid prices; the price at t = close of the minute bar starting at t−1).
  No trade if that move is exactly 0 or a price is missing.
- **Entry:** at T+30 at the real ask (long) / bid (short) of that minute.
- **Exit:** at T+150 or 15:50 NY, whichever is first (FOMC: 15:50, i.e. 80 minutes), at the real bid / ask.
- **Emergency stop:** 4 × ATR15 from the entry fill, checked on every minute's bid (long) / ask (short); fills at the
  stop, or at the minute's open if it gaps through.
- Result per trade in ATR15 (net of the spread); also shown in R with R = 4 × ATR15.

## Test (judged once)
2023-11-17 → 2026-10-01 (the seen period's second half; step 1 never read it). Halves at the elapsed midpoint.

## Gates (all required)
1. ≥ 100 trades;
2. mean net 95% range above 0 (bootstrap over release days: instruments on the same day move together);
3. mean > 0 in both halves;
4. mean > 0 at 2× costs (every spread doubled);
5. **beats the size-matched no-release control:** the same rule at 08:30 / 14:00 on weekdays with none of the four
   releases, kept only when |move T−1 → T+30| / ATR15 is at least the median of that instrument's release trades in the
   same clock group (08:30: CPI / NFP / PPI; 14:00: FOMC) in the test period. The 95% range of
   mean(release) − mean(control) (release days and control days resampled independently) must be above 0.

## Outcomes
- All five pass → a news edge; judged once on 2016–2020 (`./fx.sh newsfade vault`). Only a pass there goes to the Nov 5
  review; the news blackout is unchanged until then.
- Gates 1–4 pass but not 5 → not a news edge: "fade any big early move" is registered as a separate rule (its own test),
  nothing from this run is traded.
- Otherwise → closed; 2016–2020 is not read.

Information only (never a pass): results by release type, by instrument, with the unmatched control, and stop hits.
Note: control days can hold other releases the calendar lacks (retail sales, claims, ISM …); that dilutes, not inflates,
the difference.

---

## Addendum (Oct 28 2026, after the test-period run, before any 2016–2020 data is read): no-stop variant

The registered rule failed on 2023-11-17 → 2026-10-01 (+0.16 ATR15, −0.42..+0.77; halves +0.57 / −0.26; vs control +0.05).
Its 4 × ATR15 emergency stop fired on 145 of 361 trades: ATR15 is measured in the calm hour before the release and
post-release swings are 4–10× larger, so the stop changed the rule away from what step 1 measured (no stop). Sam chose to
test the step-1 version once:

- **news_fade_nostop:** identical to the rule above except **no stop** — exit only at T+150 or 15:50 NY.
- Judged **once** on 2016-01-01 → 2021-01-01 (`./fx.sh newsfade nostop`), with the same five gates (halves at the elapsed
  midpoint; the size-matched control built the same way within 2016–2020). The run refuses to repeat.
- This is its ONLY test (no later confirmation), and it follows a failure on 2023–2026, so a pass is weaker evidence than
  usual: it goes to the Nov 5 review as a candidate for a forward paper record only, and a live version would need a stop
  sized to post-release volatility, which would be a new rule.
