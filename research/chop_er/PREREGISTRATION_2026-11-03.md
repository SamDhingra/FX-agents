# Efficiency-ratio chop filter: pre-registration (Nov 3, 2026, before any run)

## Why

Sam asked to improve the choppy-market filter. The current one is the "Playbook + chop filter" book's routing, built
on the Choppiness Index (CHOP 14, 15-minute; ≥ 61.8 → scalps only, ≤ 38.2 → no scalps). It already failed its check
on Oct 14 (year_test/regime_365d_p2). On 840,402 research trades, the trades it dropped averaged −0.102R and the ones
it kept −0.111R, so it does not separate good markets from bad ones.

The candidate replacement is Kaufman's **efficiency ratio**:

> ER(n) = |close now − close n candles ago| ÷ (sum of the n absolute candle-to-candle changes)

It runs from 0 (all wandering, no progress) to 1 (a straight line). It is the measure in C10, the only strategy that
passed 2021–2026.

The filter here **skips** a trade in chop, rather than switching exit styles.

## Cohort, data, judge

- **Trades:** the playbook's 3m/5m entries, the same cohort and files as the room check
  (`data/year_test/playbook_test/trades_seen_*.csv.gz`, 10,724 trades, 2021-01-01 to 2026-09-30). The 2016–2020 trades
  are in `data/year_test/mtf_vault_trades/trades_old_*`.
- **Look-ahead:** measures use only 1-minute bars strictly before the entry time, and candles completed before it.
- **Judge:** the stricter judge (`whatif_judge`), the same one as the room check. A filter passes only if all of these
  hold:
  - kept trades beat flagged trades with the 95% range above 0 (circular 5-weekday blocks);
  - both calendar halves above 0 (seen split 2023-11-17);
  - stratified random-skip p < 0.05;
  - at least 30 flagged and 30 kept trades in each half;
  - at least 90% coverage.

## Checks

| check | flag (skip) when | role |
|---|---|---|
| `er15` | ER(12) of the last 12 completed 15-minute candles < 0.30 | **primary** |
| `er1h` | ER(12) of the last 12 completed 1-hour candles < 0.30 | variant (seen only) |
| `chop15_skip` | CHOP(14) 15-minute ≥ 61.8, the current filter's chop zone, used as a skip | information |
| `adx15` | ADX(14) 15-minute < 20 | information |

The 0.30 threshold is the common rule of thumb for "choppy" with this measure. It is fixed here and not tuned.

**Vault.** Only `er15`, and only if it passes on 2021–2026, is judged once on 2016–2020.

## What follows

- **If `er15` is confirmed on 2016–2020:** it becomes a shadow tag on the live playbook first, and the review decides
  whether the "Playbook + chop filter" book switches to it.
- **If it is not confirmed:** the ER filter is closed.

The current CHOP routing stays as it is either way until the review.
