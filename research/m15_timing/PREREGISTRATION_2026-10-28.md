# M15 timing: late entry on the M15 turn, early exit on M15 invalidation — pre-registration (Oct 28 2026, before any run)

Source: the losing-trade post-mortems (`./fx.sh dynpostmortem`, pm-v1, rerun on the fixed packets Oct 28). "Wait for the M15
turn" was the reviewers' most common alternative (Claude 8 of 10, OpenAI 4 of 10). The SKIP form of "M15 against the trade"
has failed three times (m15_closed, m15_impulse_leg, m15_trend); these two change WHEN the trade is entered or exited, not
which trades are taken, and have not been tested. Hindsight-generated, so tested on trades they were not drawn from.

## Cohort, engine, data
- The playbook's 3m / 5m cells, the same trades as round 3: `data/year_test/playbook_test/trades_seen_*.csv.gz`
  (2021-01-01 → 2026-10-01, 10,724 trades), 2016–2020 `data/year_test/mtf_vault_trades/trades_old_*.csv.gz`.
- Each trade is replayed by the playbook's own engine (`research.simulate_live`: live position manager on 1-minute bars,
  real bid/ask spread of every minute, the cell's own exit profile), from its signal minute, stop = the recorded
  `risk_atr` × the entry-timeframe ATR (as `research.run_job` sets it).
- **Engine check first:** the plain replay must reproduce the recorded R (|ΔR| < 0.001) on ≥ 98% of trades; otherwise
  nothing is judged and the report says the replay does not match.
- M15 candles are built from the 1-minute data, labelled by their close; a candle counts only at the minute it closes.
  The "reference candle" of a trade is the last M15 candle closed at or before the entry minute.

## A. m15_turn_entry (late entry)
- **Applies to** a trade whose reference candle closed AGAINST it (short: close > open; long: close < open). All other
  trades are entered exactly as recorded.
- **Wait** for up to the next 4 completed M15 candles (60 minutes). Confirmation = a completed M15 candle that closes in
  the trade's direction beyond the candle before it (short: close < open AND close < the previous M15 low; long: close >
  open AND close > the previous M15 high).
- **Enter** at market at that candle's closing minute (ask for longs / bid for shorts), same stop price as the original
  signal (the engine's minimum-stop rule applied as at a normal entry), same exit profile.
- **Cancel** (R = 0) if the original stop is touched first, the session flat time or the end of the entry window is
  reached, the stop is no longer on the losing side, or no confirmation within 4 candles.
- **Control (random timing):** the same applying trades, entered at the close of a random later M15 candle (1–4) or
  skipped, drawn from the rule's own distribution of outcomes (seed 11); cancelled likewise if the stop is touched first.

## B. m15_inval_exit (early exit)
- **Applies to** every trade, BEFORE its first target only (after it, the normal runner rules).
- **Exit** at market at the closing minute of the first completed M15 candle after entry that closes beyond the reference
  candle's far side (short: close above its high; long: close below its low).
- **Control (random exit):** each trade exits at market at the close of its k-th M15 candle after entry (pre-target
  only), k drawn from the rule's own firing distribution, with the same share of trades firing (seed 13).

## Gates (per check, all required)
Paired per trade: d = R(rule) − R(as recorded, replayed). Circular 5-weekday block bootstrap (10,000 draws) of the mean d.
1. ≥ 100 trades whose R changes;
2. mean d 95% range above 0;
3. mean d > 0 in both calendar halves (split 2023-11-17; vault: elapsed midpoint);
4. mean d > 0 at 2× costs (both replays with twice the spread);
5. beats its control: the 95% range of mean (R(rule) − R(control)) above 0;
6. look-ahead audit (unit tests): decisions read only candles closed by the decision minute.

## Vault and family
Each check is its own family here (entry timing; exit management) — noted: A uses the same "M15 against" signal as the
spent counterflow family, so a pass of A on 2016–2020 earns a shadow tag only. A check that passes on seen is judged ONCE
on 2016–2020 (`./fx.sh m15timing vault`); a check that fails on seen leaves the vault untouched. No trading change before
the Nov 5 review in any case.
