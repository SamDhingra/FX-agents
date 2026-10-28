# Room-to-the-next-M15-level check — pre-registration (Oct 28 2026, before any run)

Source: the losing-trade post-mortems (`./fx.sh dynpostmortem`, pm-v1). OpenAI proposed it on 3 of 10 losers, Claude in other
words on 2: "if the distance from entry to the nearest M15 low (for a short) is less than the stop distance, the trade can't
reach 1R before support — don't enter." Hindsight-generated, so it is tested here on trades it was not drawn from.

## Related, already tested (multiplicity)
`liqtest` **no_room** (nearest untaken 4H+ level ahead closer than 0.5 × ATR(1H,14)) failed on seen: −0.007R (−0.115 to +0.101).
This check differs (M15 swings, distance relative to the trade's own stop), but it is the same "room" family. Two checks run here
(one primary, one variant), so with no_room that is three tries in the family: a single seen pass is not enough on its own —
the primary must also pass once on 2016–2020.

## Cohort and data
The playbook's 3m / 5m entries (`data/year_test/playbook_test/trades_seen_*.csv.gz`, 2021-01-01 → 2026-10-01), the same
cohort and judge as round 3 (`fxagents/whatif_judge.py`: calendar halves split 2023-11-17, circular 5-weekday block bootstrap,
stratified random skipping within cell × side × hour × half, ≥ 30 per group per half, ≥ 90% coverage).
Only M1 data strictly before the entry timestamp is read.

- **entry** = close of the last M1 candle before the entry timestamp (the trade files hold no price).
- **stop distance** = `risk_atr` × ATR(14) of the entry-timeframe candles closed before entry (the reconstruction round 3 used).
- **M15 candles** = the completed 15m candles before entry from the 5 days of M1 before it; the last 16 are used.

## Checks (fixed now)
- **room_swing (primary).** Among the last 16 completed M15 candles, a swing low is a candle (not the first or the last) whose
  low is below the previous candle's low and not above the next one's; a swing high mirrors it. For a SHORT, the level ahead is
  the highest swing low below entry; for a LONG, the lowest swing high above entry. room = |entry − level|.
  **Flag when room < 1.0 × stop distance.** No swing on the target side → not flagged (open room; a real "no").
- **room_last2 (variant, OpenAI's wording).** Level ahead = the lowest low (SHORT) / highest high (LONG) of the last 2 completed
  M15 candles. Flag when 0 < room < 1.0 × stop distance; a level already broken (room ≤ 0) → not flagged.
- Information only, never a pass: room_swing at 0.75 × and 1.5 × the stop.

**Unavailable** (dropped, counted against coverage): fewer than 16 completed M15 candles, fewer than 15 entry-timeframe candles,
a non-positive ATR or `risk_atr`.

## Decision
- Seen: a check passes with the judge's gates. **room_swing decides**; room_last2 is reported beside it.
- If room_swing passes on seen: one judgement on 2016–2020 (`./fx.sh roomcheck vault`, the vault's trades from
  `mtf_vault_trades`, split at the elapsed midpoint). Only a vault pass earns a shadow tag on the live bot; trading changes are
  for the Nov 5 review. If it fails on seen, the vault is not touched.
- A pass that leaves the kept trades below zero still leaves a losing playbook (it is reported, not hidden).
