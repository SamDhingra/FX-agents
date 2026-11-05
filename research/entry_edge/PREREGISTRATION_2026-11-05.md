# Do the playbook's entries beat random timing? Pre-registration (Nov 5, 2026, before any run)

## Why

Every filter and exit tested on the playbook since October left it below zero:
- CHOP and efficiency-ratio routing and skips;
- trailing stops and early protection;
- waiting for M15;
- hours and bias variants.

The 3m/5m cohort averages −0.095R per trade.

Astra's review of the chop filter (Nov 5) recommends testing the entries themselves first. If the setups' entries do no
better than entering at a random moment with the same stop and exit, no market-state filter or exit change can make the
playbook pay. The problem is then the setups, not the conditions around them.

This test answers that question directly.

## Cohort and engine

- **Trades:** every playbook research trade, 2021-01-01 to 2026-09-30, all timeframes and exit profiles
  (`data/year_test/playbook_test/trades_seen_*.csv.gz`). The vault trades are in
  `data/year_test/mtf_vault_trades/trades_old_*`.
- **Engine:** the playbook's own engine (`research.simulate_live`), with the real per-minute bid/ask spread and each
  trade's own exit profile, flat time and maximum hold.
- **Engine check:** the plain replay must reproduce the recorded R on at least 98% of trades. Only reproduced trades are
  judged.

## Controls (built from the same trade, changing one thing)

| control | what changes | what stays the same | role |
|---|---|---|---|
| `rand_time` | the entry moment: a random candle close of the same timeframe on the same trading day, inside the entry windows (not in the last 20 minutes before the flat time), different from the real one | instrument, timeframe, direction, stop distance in ATR (at the new candle), exit profile | **primary** |
| `opposite` | the direction: the same entry moment, the other side | everything else | information |

- **Draws:** `rand_time` uses 5 independent draws per trade (seed 20261105), averaged per trade.
- **Unavailable controls:** a trade whose day has no other valid candle has no `rand_time` control and is left out of
  that comparison.

## Gates

- **The entries' timing edge:** d = R(real) − mean R(rand_time draws) per trade.
- **What counts as an edge:** all of these must hold:
  - at least 100 trades compared;
  - the 95% range of the mean d is above 0 (circular 5-weekday blocks, 10,000 draws);
  - both halves are above 0 (split 2023-11-17);
  - the mean d is above 0 at 2× costs (every arm at 2× spread).
- **Also reported, information only:**
  - real vs control average R, overall and by instrument, timeframe, exit profile and setup;
  - the `opposite` comparison (direction skill).

## What follows

- **The entries beat random timing on 2021–2026:** the setups do find better moments. The losses then come from what
  happens after entry (costs relative to the stop, exits), and those get the next tests. The edge is judged once on
  2016–2020.
- **They don't:** the setups' timing adds nothing over a random entry with the same stop and exit. Filters and exits on
  top of them can't make the playbook pay. The review should then:
  - stop tuning the playbook;
  - decide between retiring it and rebuilding the setups.

Nothing in trading changes from this test by itself.
