# Protection for the playbook's trend-profile trades: pre-registration (Nov 4, 2026, before any run)

## Why

On Nov 4 the "Playbook, no bias" paper book shorted US30 with `dtfx_close_fib:15m@pb-us30-15ba-trend`. The trade went
+1.34R, turned, and was stopped out at −1.00R.

That isn't a fault; it follows from the cell's exit profile. Cells ending in `-trend` (15-minute and slower) use the
**trend** profile:
- the first target is 2R;
- the configured partial is banked there, and the runner is held up to 8 hours;
- **nothing protects the trade before +2R.**

The standard profile banks 50% at +1R and moves the stop to +0.1R; the trend profile does not. So a trend trade that
reaches +1.9R can still lose the full 1R.

The Oct 19 exit study (year_test/exit_study) tested early protection on all playbook cells over one year. It found
nothing above noise overall. Per cell, break-even at +0.5R looked better on the trend cells (e.g. NDQ wick-fib trend
+0.158 vs +0.125, US30 S/R trend +0.177 vs +0.147). Those cells were never judged on their own, so this test is
restricted to trend-profile trades only.

## Cohort and engine

- **Trades:** every playbook research trade whose exit profile is `trend`, 2021-01-01 to 2026-09-30
  (`data/year_test/playbook_test/trades_seen_*.csv.gz`). The vault trades are in
  `data/year_test/mtf_vault_trades/trades_old_*`.
- **Engine:** the playbook's own engine (`research.simulate_live`), with the real per-minute bid/ask spread and the same
  stop, flat time and 8-hour hold.
- **Engine check:** the plain replay must reproduce the recorded R on at least 98% of trades. Only reproduced trades are
  judged.

## Rules (each changes only what happens before the first target)

| rule | what it does | role |
|---|---|---|
| `lock1` | once the best price reaches +1R, the stop moves to +0.1R | **primary** |
| `be05` | once +0.5R, the stop moves to break-even | information |
| `half1` | at +1R, bank 50% and move the stop to +0.1R (what the standard profile does) | information |

**Gates** (`lock1`, d = R(rule) − R(today) per trade). All of these are required:
- at least 100 trades changed;
- the 95% range of the mean d is above 0 (circular 5-weekday blocks, 10,000 draws);
- both halves are above 0 (split 2023-11-17);
- the mean d is above 0 at 2× costs (both sides at 2× spread).

**Vault.** If `lock1` passes, it is judged once on 2016–2020.

Also shown:
- how many trend trades reach +1R and still close at a loss today (the Nov 4 pattern);
- what each rule does to the trades that make 2R or more today.

## What follows

- **If `lock1` is confirmed on 2016–2020:** the trend profile gets "+0.1R stop at +1R" on the paper books first. The
  review decides on the account.
- **If it is not confirmed:** the trend profile stays as it is.
