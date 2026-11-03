# Wait one M15 candle before entering against a fresh M15 close: pre-registration (Nov 2, 2026, before any run)

## Where it comes from

In the M15 timing test (research/m15_timing, Oct 28), rule A delayed entries whose last completed 15-minute candle had
closed **against** the trade, waiting for a confirming candle. It improved the playbook's 3m/5m trades by +0.013R per
trade (95% range +0.004 to +0.022). A random-timing control did just as well: entering at a random later 15-minute
close, or skipping. So the confirmation signal added nothing. The gain came from **waiting** and skipping trades whose
stop was touched while waiting.

This registration tests the simplest form of that: a fixed one-candle wait. 2021–2026 shaped the idea, so it gets
**one judgement on 2016–2020**, which no version of it has touched.

## Rule `m15_wait1`

- **Which trades.** A playbook 3m/5m trade whose reference candle closed against it: for a long, close < open; for a
  short, close > open. The reference candle is the last 15-minute candle closed at or before the entry minute. All
  other trades are left exactly as recorded.
- **Wait.** Wait for the **next** 15-minute candle to close, then enter at market at its closing minute: the ask for
  longs, the bid for shorts. No confirmation is required.
- **Stop and exits.** The same stop price as the original signal, with the engine's minimum-stop and maximum-stop rules
  applied as at a normal entry. The same exit profile.
- **Cancel** (R = 0) if:
  - the original stop is touched on the bid/ask while waiting;
  - the session flat time is reached;
  - the entry window has ended at that candle;
  - the stop is no longer on the losing side.
- **Engine.** Identical to the M15 timing test: the playbook's own engine (`research.simulate_live`), the real per-minute
  bid/ask spread, and the vault trades in `data/year_test/mtf_vault_trades/trades_old_*.csv.gz`. Before anything is
  judged, an engine check must reproduce the recorded R on at least 98% of trades.

## Gates

On 2016-01-01 to 2020-12-31, judged once, all required:

- **Size:** at least 100 trades changed.
- **Mean d above 0:** where d = R(rule) − R(as recorded), the 95% range of the mean d must be above 0 (circular
  5-weekday block bootstrap, 10,000 draws).
- **Both halves:** both calendar halves above 0, split at the period's middle.
- **Costs:** the mean d still above 0 at twice the spread.

The same rule on 2021–2026 is shown for reference only; that period is where the idea came from.

## What follows

- **If it passes:** it becomes a shadow tag on the live playbook (log "would have waited"), and the review decides.
- **If it fails:** the "wait for M15" family is closed.

The playbook averages −0.095R per trade, so even a confirmed +0.01–0.02R would leave it losing. The rule matters only as
part of a playbook that is positive in its own right.

## Outcome (Nov 2, 2026): passes its 2016–2020 judgement, narrowly

| period | trades changed | mean d (95% range) | halves | 2× costs |
|---|---|---|---|---|
| 2016–2020 (judged) | 1,757 of 9,120 | +0.009 (+0.001 to +0.017) | +0.010 / +0.008 | +0.020 |
| 2021–2026 (shown) | 1,895 of 10,724 | +0.002 (−0.005 to +0.009) | +0.001 / +0.003 | +0.009 |

Engine check 100% in both periods.

**Correction to the "untouched" claim above.** Round 3 (Oct 26) declared that the "counterflow" family shares one
use of the 2016–2020 data: m15_live (the 15-minute candle in progress against the trade), A1, and a wait-for-the-15m
policy. That use went to m15_live's confirmation, which failed. m15_wait1 itself had never been run on those years,
but a closely related signal had. This narrow pass is therefore weaker evidence than a first use would be.

The exact rule is also near zero on 2021–2026 (+0.002R). The earlier +0.013R came from the confirm-or-wait version.

**Decision, as registered:** a shadow tag only. Live trades record `m15_wait` (whether the last completed M15 candle
closed against the entry) and a `m15_wait_tag` timeline event. Any trading change is for the review, and even a real
+0.01R leaves the playbook below zero.
