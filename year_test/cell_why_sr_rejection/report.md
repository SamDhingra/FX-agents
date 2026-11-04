Rules: NDQ InstrumentRule(role='selective', min_p=0.0, min_e=0.03, max_cells=4, max_positions=1, k_p=40.0, min_n=30); US30 InstrumentRule(role='selective', min_p=0.0, min_e=0.03, max_cells=4, max_positions=1, k_p=40.0, min_n=30)

# Why isn't sr_rejection trading?

Playbook in use: as of 2026-11-03 (file written 2026-11-04 14:59 UTC), 30 cells; sr_rejection: sr_rejection:30m@pb-us30-d-trend
Research trades: 2026-08-04 → 2026-11-02 (65 trading days). Window: 60 trading days.

## Day by day (selection made at the start of each day)

- 2026-10-15: no cell selected
- 2026-10-16: US30 30min default std selected
- 2026-10-19: no cell selected
- 2026-10-20: no cell selected
- 2026-10-21: no cell selected
- 2026-10-22: NDQ 30min default std selected
- 2026-10-23: NDQ 30min default std selected
- 2026-10-26: no cell selected
- 2026-10-27: no cell selected
- 2026-10-28: no cell selected
- 2026-10-29: US30 30min default trend selected
- 2026-10-30: US30 30min default trend selected
- 2026-11-02: US30 30min default trend selected
- next: US30 30min default trend selected

## Its cells now (window ending at the last research day)

| sym | tf | variant | exit | trades | avg R | shrunk e | halves | verdict |
|---|---|---|---|---|---|---|---|---|
| NDQ | 30min | default | std | 32 | +0.029 | -0.021 | +0.193 / -0.210 | a half of the window is not positive (+0.193 / -0.210); shrunk expectancy -0.021 < +0.030 |
| NDQ | 3min | default | scalp | 312 | -0.027 | -0.030 | -0.029 / -0.025 | a half of the window is not positive (-0.029 / -0.025); shrunk expectancy -0.030 < +0.030 |
| NDQ | 3min | default | std | 295 | -0.028 | -0.030 | -0.033 / -0.024 | a half of the window is not positive (-0.033 / -0.024); shrunk expectancy -0.030 < +0.030 |
| NDQ | 30min | default | trend | 30 | +0.067 | -0.033 | +0.376 / -0.339 | a half of the window is not positive (+0.376 / -0.339); shrunk expectancy -0.033 < +0.030 |
| NDQ | 15min | default | std | 59 | -0.061 | -0.048 | -0.093 / -0.023 | a half of the window is not positive (-0.093 / -0.023); shrunk expectancy -0.048 < +0.030 |
| NDQ | 5min | default | scalp | 187 | -0.055 | -0.053 | -0.064 / -0.043 | a half of the window is not positive (-0.064 / -0.043); shrunk expectancy -0.053 < +0.030 |
| NDQ | 5min | default | std | 181 | -0.077 | -0.070 | -0.089 / -0.064 | a half of the window is not positive (-0.089 / -0.064); shrunk expectancy -0.070 < +0.030 |
| NDQ | 1h | default | std | 17 | -0.078 | -0.071 | +0.001 / -0.671 | only 17 trades in the window (needs 30); a half of the window is not positive (+0.001 / -0.671); shrunk expectancy -0.071 < +0.030 |
| NDQ | 15min | default | trend | 57 | -0.185 | -0.152 | -0.246 / -0.106 | a half of the window is not positive (-0.246 / -0.106); shrunk expectancy -0.152 < +0.030 |
| NDQ | 1h | default | trend | 16 | -0.092 | -0.156 | +0.040 / -1.013 | only 16 trades in the window (needs 30); a half of the window is not positive (+0.040 / -1.013); shrunk expectancy -0.156 < +0.030 |
| US30 | 30min | default | trend | 35 | +0.189 | +0.102 | +0.088 / +0.274 | selected |
| US30 | 30min | default | std | 35 | +0.088 | +0.048 | +0.095 / +0.083 | ranked 11 on US30, only the top 4 are kept |
| US30 | 1h | default | std | 11 | +0.092 | +0.025 | -0.288 / +0.310 | only 11 trades in the window (needs 30); a half of the window is not positive (-0.288 / +0.310); shrunk expectancy +0.025 < +0.030 |
| US30 | 5min | default | std | 149 | +0.026 | +0.017 | -0.023 / +0.083 | a half of the window is not positive (-0.023 / +0.083); shrunk expectancy +0.017 < +0.030 |
| US30 | 1h | default | trend | 11 | +0.044 | +0.012 | -0.241 / +0.206 | only 11 trades in the window (needs 30); a half of the window is not positive (-0.241 / +0.206); shrunk expectancy +0.012 < +0.030 |
| US30 | 5min | default | scalp | 156 | +0.015 | +0.006 | -0.014 / +0.048 | a half of the window is not positive (-0.014 / +0.048); shrunk expectancy +0.006 < +0.030 |
| US30 | 3min | default | std | 249 | -0.002 | -0.001 | -0.039 / +0.031 | a half of the window is not positive (-0.039 / +0.031); shrunk expectancy -0.001 < +0.030 |
| US30 | 3min | default | scalp | 259 | -0.016 | -0.016 | -0.041 / +0.004 | a half of the window is not positive (-0.041 / +0.004); shrunk expectancy -0.016 < +0.030 |
| US30 | 15min | default | std | 60 | -0.030 | -0.020 | -0.122 / +0.074 | a half of the window is not positive (-0.122 / +0.074); shrunk expectancy -0.020 < +0.030 |
| US30 | 15min | default | trend | 56 | -0.100 | -0.065 | -0.166 / -0.024 | a half of the window is not positive (-0.166 / -0.024); shrunk expectancy -0.065 < +0.030 |
| XAUUSD | 3min | default | std | 343 | -0.024 | -0.024 | -0.023 / -0.025 | a half of the window is not positive (-0.023 / -0.025); shrunk expectancy -0.024 < +0.020 |
| XAUUSD | 3min | default | scalp | 359 | -0.026 | -0.026 | -0.029 / -0.024 | a half of the window is not positive (-0.029 / -0.024); shrunk expectancy -0.026 < +0.020 |
| XAUUSD | 5min | default | scalp | 219 | -0.039 | -0.036 | -0.029 / -0.048 | a half of the window is not positive (-0.029 / -0.048); shrunk expectancy -0.036 < +0.020 |
| XAUUSD | 5min | default | std | 208 | -0.058 | -0.053 | -0.056 / -0.059 | a half of the window is not positive (-0.056 / -0.059); shrunk expectancy -0.053 < +0.020 |
| XAUUSD | 15min | default | std | 80 | -0.042 | -0.059 | -0.091 / +0.006 | a half of the window is not positive (-0.091 / +0.006); shrunk expectancy -0.059 < +0.020 |
| XAUUSD | 30min | default | std | 43 | -0.098 | -0.100 | -0.003 / -0.155 | a half of the window is not positive (-0.003 / -0.155); shrunk expectancy -0.100 < +0.020 |
| XAUUSD | 15min | default | trend | 79 | -0.090 | -0.102 | -0.183 / +0.001 | a half of the window is not positive (-0.183 / +0.001); shrunk expectancy -0.102 < +0.020 |
| XAUUSD | 30min | default | trend | 43 | -0.136 | -0.124 | -0.060 / -0.180 | a half of the window is not positive (-0.060 / -0.180); shrunk expectancy -0.124 < +0.020 |
| XAUUSD | 1h | default | std | 22 | -0.336 | -0.174 | -0.369 / -0.314 | only 22 trades in the window (needs 25); a half of the window is not positive (-0.369 / -0.314); shrunk expectancy -0.174 < +0.020 |
| XAUUSD | 1h | default | trend | 22 | -0.496 | -0.251 | -0.531 / -0.472 | only 22 trades in the window (needs 25); a half of the window is not positive (-0.531 / -0.472); shrunk expectancy -0.251 < +0.020 |

## Last trade of it in each journal

- journal.sqlite: 59 trades, last opened 2026-10-29T04:40:03.176425-04:00
- journal_c10_afternoon.sqlite: 0 trades, last opened —
- journal_daily_rsi2_adx2.sqlite: 0 trades, last opened —
- journal_ema21_rsi55.sqlite: 0 trades, last opened —
- journal_gold_breakout.sqlite: 0 trades, last opened —
- journal_h1_vol_trend.sqlite: 0 trades, last opened —
- journal_playbook.sqlite: 5 trades, last opened 2026-10-27T02:00:08.463643-04:00
- journal_playbook_allhours.sqlite: 0 trades, last opened —
- journal_playbook_nobias.sqlite: 3 trades, last opened 2026-11-02T10:30:03.866549-05:00
- journal_playbook_regime.sqlite: 2 trades, last opened 2026-10-22T11:00:04.802773-04:00
- journal_playbook_regime_nobias.sqlite: 0 trades, last opened —
- journal_setup_first.sqlite: 25 trades, last opened 2026-10-08T09:35:06.041724-04:00
- journal_shadow.sqlite: 0 trades, last opened —

## Its signals since the playbook last picked it up, per playbook book (what each book did and why)

### journal.sqlite

- 2026-11-04T02:50 US30 SHORT → rejected: index group full (one index position per direction at a time)
- 2026-11-03T21:00 US30 SHORT → rejected: cost 0.16R of the stop (spread 5 vs stop 30.5) > cap 0.08R
- 2026-11-03T20:35 US30 LONG → rejected: counter-bias reversal not confirmed by Jev (0.33)
- 2026-11-03T15:45 US30 SHORT → rejected: outside entry windows
- 2026-11-03T14:25 US30 SHORT → rejected: index group full (one index position per direction at a time)
- 2026-11-03T11:50 US30 SHORT → rejected: outside entry windows
- 2026-11-03T11:25 US30 LONG → rejected: counter-bias reversal not confirmed by Jev (0.31)
- 2026-10-30T10:00 NDQ LONG → filtered: counter to BEARISH bias
- 2026-10-30T09:50 US30 SHORT → filtered: counter to BULLISH bias
- 2026-10-30T09:15 NDQ LONG → filtered: counter to BEARISH bias
- 2026-10-30T09:05 US30 SHORT → filtered: counter to BULLISH bias
- 2026-10-30T04:40 NDQ LONG → filtered: counter to BEARISH bias
- 2026-10-30T04:00 NDQ LONG → filtered: counter to BEARISH bias
- 2026-10-29T20:40 US30 LONG → filtered: bias neutral (-0.20)
- 2026-10-29T04:40 NDQ SHORT → taken: qty 3.91, risk $124, cost 0.07R

### journal_playbook.sqlite

- 2026-11-04T07:30 US30 LONG → rejected: trading halted: max drawdown hit (-6.0% from peak)
- 2026-11-04T06:00 US30 LONG → rejected: trading halted: max drawdown hit (-6.0% from peak)
- 2026-11-03T20:30 US30 LONG → skipped: playbook: US30 already has 1 position(s)
- 2026-11-02T19:30 US30 LONG → rejected: outside entry windows
- 2026-11-02T15:30 US30 SHORT → skipped: playbook: US30 already has 1 position(s)
- 2026-11-02T10:30 US30 LONG → rejected: counter to BEARISH bias (exception needs raid ✗ + 1H shift ✓)
- 2026-11-02T05:30 US30 LONG → rejected: outside entry windows
- 2026-10-30T08:30 US30 SHORT → filtered: counter to BULLISH bias
- 2026-10-30T04:30 US30 SHORT → filtered: bias neutral (-0.20)
- 2026-10-29T23:30 US30 LONG → filtered: bias neutral (-0.20)
- 2026-10-29T20:00 US30 LONG → filtered: bias neutral (-0.20)
- 2026-10-29T17:00 US30 LONG → filtered: bias neutral (-0.20)
- 2026-10-29T12:30 US30 SHORT → filtered: bias neutral (-0.20)
- 2026-10-29T11:00 US30 LONG → filtered: bias neutral (-0.20)
- 2026-10-29T09:00 US30 LONG → filtered: bias neutral (-0.20)

### journal_playbook_allhours.sqlite

- 2026-11-04T07:30 US30 LONG → rejected: counter to BEARISH bias (exception needs raid ✗ + 1H shift ✓)
- 2026-11-04T06:00 US30 LONG → rejected: counter to BEARISH bias (exception needs raid ✗ + 1H shift ✓)
- 2026-11-03T20:30 US30 LONG → skipped: playbook: US30 already has 1 position(s)
- 2026-11-02T19:30 US30 LONG → rejected: outside entry windows
- 2026-11-02T15:30 US30 SHORT → skipped: playbook: US30 already has 1 position(s)
- 2026-11-02T10:30 US30 LONG → rejected: counter to BEARISH bias (exception needs raid ✗ + 1H shift ✓)
- 2026-11-02T05:30 US30 LONG → rejected: counter-bias reversal not confirmed by Jev (0.34)
- 2026-10-30T08:30 US30 SHORT → filtered: counter to BULLISH bias
- 2026-10-30T04:30 US30 SHORT → filtered: bias neutral (-0.20)
- 2026-10-29T23:30 US30 LONG → filtered: bias neutral (-0.20)
- 2026-10-29T20:00 US30 LONG → filtered: bias neutral (-0.20)
- 2026-10-29T17:00 US30 LONG → filtered: bias neutral (-0.20)

### journal_playbook_nobias.sqlite

- 2026-11-04T07:30 US30 LONG → rejected: outside entry windows
- 2026-11-04T06:00 US30 LONG → rejected: outside entry windows
- 2026-11-03T20:30 US30 LONG → skipped: playbook: US30 already has 1 position(s)
- 2026-11-02T19:30 US30 LONG → rejected: outside entry windows
- 2026-11-02T15:30 US30 SHORT → skipped: playbook: US30 already has 1 position(s)
- 2026-11-02T10:30 US30 LONG → taken: qty 1.01, risk $177, cost 0.02R
- 2026-11-02T05:30 US30 LONG → rejected: outside entry windows
- 2026-10-30T08:30 US30 SHORT → rejected: news blackout: Employment Cost Index q/q (medium, after)
- 2026-10-30T04:30 US30 SHORT → skipped: playbook: US30 already has 1 position(s)
- 2026-10-29T23:30 US30 LONG → taken: qty 1.27, risk $88, cost 0.04R
- 2026-10-29T20:00 US30 LONG → taken: qty 1.59, risk $88, cost 0.05R
- 2026-10-29T17:00 US30 LONG → rejected: outside entry windows

### journal_playbook_regime.sqlite

- 2026-11-04T07:30 US30 LONG → rejected: outside entry windows
- 2026-11-04T06:00 US30 LONG → rejected: outside entry windows
- 2026-11-03T20:30 US30 LONG → skipped: regime chop (Jev chop 0.82, CHOP 44.5): scalps only
- 2026-11-02T19:30 US30 LONG → skipped: regime chop (Jev chop 0.86, CHOP 42.9): scalps only
- 2026-11-02T15:30 US30 SHORT → skipped: regime chop (Jev chop 0.75, CHOP 51.7): scalps only
- 2026-11-02T10:30 US30 LONG → rejected: counter to BEARISH bias (exception needs raid ✗ + 1H shift ✓)
- 2026-11-02T05:30 US30 LONG → rejected: outside entry windows
- 2026-10-30T08:30 US30 SHORT → filtered: counter to BULLISH bias
- 2026-10-30T04:30 US30 SHORT → filtered: bias neutral (-0.20)
- 2026-10-29T23:30 US30 LONG → filtered: bias neutral (-0.20)
- 2026-10-29T20:00 US30 LONG → filtered: bias neutral (-0.20)
- 2026-10-29T17:00 US30 LONG → filtered: bias neutral (-0.20)
- 2026-10-29T12:30 US30 SHORT → filtered: bias neutral (-0.20)
- 2026-10-29T11:00 US30 LONG → filtered: bias neutral (-0.20)
- 2026-10-29T09:00 US30 LONG → filtered: bias neutral (-0.20)

