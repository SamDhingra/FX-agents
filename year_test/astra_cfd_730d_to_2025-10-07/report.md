# Audit strategies (ASTRA-*-CFD-001 v0.1.0) — 730 days

**Data only up to 2025-10-07** (out-of-sample check).

History: /app/data/history_730d. Rules exactly as in docs/astra_audit_2026-10-08.md §4; nothing tuned. R per trade after spread + slippage (spread NDQ 1.50 / US30 2.50 / XAUUSD 0.40, slippage max(tick, ¼ spread) per market/stop fill). 95% = bootstrap interval of the average R (at most one trade per day, so trades are day blocks). ×1.5 / ×2 = the same trades with costs scaled.

Warm-up deviation: the spec asks for 500 bars of the longest indicator timeframe; with 365 days the gap test uses ≥ 20 prior daily bars and the others ≥ 150 bars. Instruments are tested separately (no one-index-position rule).

## Summary

| strategy | test | sym | trades | win | avg R | 95% | total R | PF | t | ×1.5 avg | ×2 avg | halves | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ORB-EXP | spec | NDQ | 27 | 33% | -0.372 | -0.72 … +0.02 | -10.0 | 0.45 | -1.97 | -0.383 | -0.393 | -0.51 / -0.25 | too few trades (27) to judge |
| ORB-EXP | spec | US30 | 27 | 41% | +0.004 | -0.48 … +0.55 | +0.1 | 1.01 | +0.01 | -0.011 | -0.025 | -0.17 / +0.17 | too few trades (27) to judge |
| ORB-EXP | control: no W/M or close-location filter | NDQ | 91 | 34% | -0.121 | -0.42 … +0.22 | -11.0 | 0.82 | -0.74 | -0.136 | -0.150 | -0.17 / -0.07 | better than spec |
| ORB-EXP | control: no W/M or close-location filter | US30 | 76 | 39% | +0.081 | -0.25 … +0.44 | +6.2 | 1.13 | +0.44 | +0.061 | +0.044 | +0.29 / -0.13 | better than spec |
| GAP-FAIL | spec | NDQ | 0 | | | | | | | | | | no trades |
| GAP-FAIL | spec | US30 | 0 | | | | | | | | | | no trades |
| GAP-FAIL | control: unconditional small-gap fade | NDQ | 32 | 28% | -0.301 | -0.69 … +0.13 | -9.6 | 0.58 | -1.40 | -0.315 | -0.329 | -0.29 / -0.31 |  |
| GAP-FAIL | control: unconditional small-gap fade | US30 | 18 | 28% | -0.183 | -0.71 … +0.46 | -3.3 | 0.72 | -0.58 | -0.197 | -0.212 | -0.35 / -0.01 |  |
| H1-VOL-TREND | spec | XAUUSD | 60 | 58% | +0.105 | -0.08 … +0.30 | +6.3 | 1.42 | +1.07 | +0.087 | +0.069 | +0.01 / +0.20 | fail — 95% interval includes zero (unproven) |
| H1-VOL-TREND | spec | NDQ | 45 | 49% | -0.065 | -0.35 … +0.23 | -2.9 | 0.86 | -0.43 | -0.102 | -0.110 | +0.12 / -0.24 | fail — average R ≤ 0; 2× costs turn it negative; no better than its control |
| H1-VOL-TREND | control: plain 12-bar breakout | XAUUSD | 166 | 54% | +0.087 | -0.04 … +0.22 | +14.4 | 1.32 | +1.32 | +0.069 | +0.052 | +0.04 / +0.13 |  |
| H1-VOL-TREND | control: plain 12-bar breakout | NDQ | 188 | 48% | +0.057 | -0.10 … +0.21 | +10.7 | 1.14 | +0.71 | +0.041 | +0.032 | +0.25 / -0.14 | better than spec |
| H1-VOL-TREND | control: 10:00 entry with the EMA trend | XAUUSD | 235 | 51% | -0.026 | -0.13 … +0.08 | -6.1 | 0.92 | -0.49 | -0.042 | -0.057 | +0.00 / -0.05 |  |
| H1-VOL-TREND | control: 10:00 entry with the EMA trend | NDQ | 235 | 49% | +0.000 | -0.12 … +0.13 | +0.0 | 1.00 | +0.00 | -0.008 | -0.020 | -0.02 / +0.02 | better than spec |

Verdict rule (frozen before the run): PROMISING needs ≥ 30 trades, average R > 0, the 95% interval above zero, average R > 0 at 2× costs, and a better average than its best control. Anything else fails; a positive average with an interval spanning zero is 'unproven', not a pass.

## Detail

### ORB-EXP · NDQ · spec

- 27 trades 2024-10-08 → 2025-10-07, worst drawdown -14.3R
- quarters (avg R): -0.759 · -0.325 · -0.572 · +0.259
- by month (trades, R): 2024-11 +0.7 (1) · 2024-12 -2.0 (2) · 2025-01 -4.0 (4) · 2025-02 +0.1 (1) · 2025-03 +1.6 (2) · 2025-04 -3.0 (3) · 2025-05 -1.0 (1) · 2025-06 +1.0 (2) · 2025-07 -2.0 (2) · 2025-08 -3.4 (6) · 2025-09 +1.9 (3)
- sides: short 11 trades -0.794R, long 16 trades -0.082R
- exits: stop 26, time 1

### ORB-EXP · US30 · spec

- 27 trades 2024-10-08 → 2025-10-07, worst drawdown -8.8R
- quarters (avg R): +0.280 · -0.747 · +0.064 · +0.487
- by month (trades, R): 2024-11 -1.0 (1) · 2024-12 +0.6 (3) · 2025-01 +2.4 (3) · 2025-02 -3.0 (3) · 2025-03 -0.2 (2) · 2025-04 -2.0 (2) · 2025-05 -0.3 (6) · 2025-06 +0.8 (1) · 2025-07 -1.0 (1) · 2025-08 -2.0 (2) · 2025-09 +6.0 (3)
- sides: short 12 trades +0.170R, long 15 trades -0.130R
- exits: stop 26, time 1

### ORB-EXP · NDQ · control: no W/M or close-location filter

- 91 trades 2024-10-08 → 2025-10-07, worst drawdown -21.4R
- quarters (avg R): -0.401 · +0.026 · -0.272 · +0.177
- by month (trades, R): 2024-11 -3.3 (5) · 2024-12 +0.7 (8) · 2025-01 -4.1 (6) · 2025-02 -4.4 (7) · 2025-03 +6.0 (9) · 2025-04 -3.5 (11) · 2025-05 -5.4 (10) · 2025-06 -0.8 (9) · 2025-07 -1.4 (7) · 2025-08 -3.5 (9) · 2025-09 +6.3 (8) · 2025-10 +2.5 (2)
- sides: short 46 trades -0.353R, long 45 trades +0.116R
- exits: stop 89, trail_through 1, time 1

### ORB-EXP · US30 · control: no W/M or close-location filter

- 76 trades 2024-10-08 → 2025-10-07, worst drawdown -16.1R
- quarters (avg R): +0.433 · +0.157 · -0.556 · +0.291
- by month (trades, R): 2024-11 +0.2 (5) · 2024-12 +7.7 (9) · 2025-01 -0.6 (6) · 2025-02 +1.2 (7) · 2025-03 +5.3 (7) · 2025-04 -6.2 (9) · 2025-05 -6.8 (14) · 2025-06 -2.9 (8) · 2025-07 +4.9 (3) · 2025-08 -2.0 (2) · 2025-09 +5.6 (6)
- sides: short 39 trades -0.115R, long 37 trades +0.288R
- exits: stop 74, time 2

### GAP-FAIL · NDQ · control: unconditional small-gap fade

- 32 trades 2024-10-08 → 2025-10-07, worst drawdown -13.8R
- quarters (avg R): -0.166 · -0.413 · -0.255 · -0.371
- by month (trades, R): 2024-11 -2.0 (2) · 2025-01 +3.7 (3) · 2025-02 -2.0 (2) · 2025-03 -1.0 (4) · 2025-04 -3.0 (3) · 2025-05 -2.3 (4) · 2025-06 +2.3 (2) · 2025-07 -1.3 (3) · 2025-08 -2.4 (5) · 2025-09 -3.0 (3) · 2025-10 +1.4 (1)
- sides: short 17 trades -0.213R, long 15 trades -0.402R
- exits: stop 23, time 5, target 4

### GAP-FAIL · US30 · control: unconditional small-gap fade

- 18 trades 2024-10-08 → 2025-10-07, worst drawdown -9.3R
- quarters (avg R): +0.118 · -0.952 · -0.432 · +0.651
- by month (trades, R): 2024-12 +1.4 (2) · 2025-01 +0.2 (2) · 2025-02 -1.7 (2) · 2025-03 -3.0 (3) · 2025-04 -3.0 (3) · 2025-06 +1.3 (1) · 2025-07 -1.0 (1) · 2025-09 +3.6 (3) · 2025-10 -1.0 (1)
- sides: short 5 trades -0.069R, long 13 trades -0.227R
- exits: stop 11, target 4, time 3

### H1-VOL-TREND · XAUUSD · spec

- 60 trades 2024-10-08 → 2025-10-07, worst drawdown -4.3R
- quarters (avg R): -0.021 · +0.037 · +0.192 · +0.211
- by month (trades, R): 2024-10 -0.0 (4) · 2024-11 +0.5 (2) · 2024-12 +0.2 (4) · 2025-01 -1.2 (10) · 2025-02 -1.9 (5) · 2025-03 +2.2 (4) · 2025-04 +1.2 (3) · 2025-05 +1.0 (4) · 2025-06 -0.2 (4) · 2025-07 +0.5 (6) · 2025-08 +1.0 (4) · 2025-09 +2.7 (9) · 2025-10 +0.2 (1)
- sides: short 10 trades -0.214R, long 50 trades +0.169R
- exits: time 51, stop 9

### H1-VOL-TREND · NDQ · spec

- 45 trades 2024-10-08 → 2025-10-07, worst drawdown -9.7R
- quarters (avg R): +0.132 · -0.003 · -0.175 · -0.230
- by month (trades, R): 2024-10 -0.8 (2) · 2024-11 +4.6 (2) · 2024-12 -0.2 (6) · 2025-01 -2.6 (3) · 2025-02 +1.4 (4) · 2025-03 -0.8 (6) · 2025-04 -0.3 (2) · 2025-05 -0.2 (3) · 2025-06 -0.1 (3) · 2025-07 -0.3 (2) · 2025-08 -2.3 (4) · 2025-09 -1.2 (8)
- sides: short 16 trades -0.143R, long 29 trades -0.021R
- exits: time 25, stop 20

### H1-VOL-TREND · XAUUSD · control: plain 12-bar breakout

- 166 trades 2024-10-08 → 2025-10-07, worst drawdown -8.5R
- quarters (avg R): +0.176 · -0.091 · +0.069 · +0.195
- by month (trades, R): 2024-10 +1.9 (8) · 2024-11 +0.2 (11) · 2024-12 +6.2 (17) · 2025-01 -2.6 (17) · 2025-02 -1.9 (15) · 2025-03 -0.4 (11) · 2025-04 +1.2 (15) · 2025-05 +3.6 (11) · 2025-06 -2.5 (16) · 2025-07 +0.3 (17) · 2025-08 +1.9 (14) · 2025-09 +6.2 (10) · 2025-10 +0.3 (4)
- sides: short 65 trades +0.059R, long 101 trades +0.105R
- exits: time 139, stop 27

### H1-VOL-TREND · NDQ · control: plain 12-bar breakout

- 188 trades 2024-10-08 → 2025-10-07, worst drawdown -17.2R
- quarters (avg R): +0.352 · +0.155 · -0.157 · -0.122
- by month (trades, R): 2024-10 +6.2 (8) · 2024-11 -0.6 (15) · 2024-12 +8.3 (15) · 2025-01 +2.7 (14) · 2025-02 -0.7 (18) · 2025-03 +5.9 (18) · 2025-04 +0.1 (16) · 2025-05 -1.2 (14) · 2025-06 -1.3 (14) · 2025-07 -2.6 (17) · 2025-08 -4.3 (18) · 2025-09 -0.9 (17) · 2025-10 -0.9 (4)
- sides: short 82 trades +0.004R, long 106 trades +0.098R
- exits: time 109, stop 79

### H1-VOL-TREND · XAUUSD · control: 10:00 entry with the EMA trend

- 235 trades 2024-10-08 → 2025-10-07, worst drawdown -19.3R
- quarters (avg R): +0.021 · -0.013 · -0.179 · +0.068
- by month (trades, R): 2024-10 +1.3 (11) · 2024-11 +2.6 (20) · 2024-12 -0.6 (20) · 2025-01 -2.2 (19) · 2025-02 -4.8 (19) · 2025-03 +2.6 (20) · 2025-04 +0.8 (21) · 2025-05 -2.2 (20) · 2025-06 -5.6 (19) · 2025-07 -3.1 (20) · 2025-08 +3.1 (21) · 2025-09 +2.3 (20) · 2025-10 -0.2 (5)
- sides: short 81 trades -0.151R, long 154 trades +0.040R
- exits: time 180, stop 55

### H1-VOL-TREND · NDQ · control: 10:00 entry with the EMA trend

- 235 trades 2024-10-08 → 2025-10-07, worst drawdown -9.6R
- quarters (avg R): -0.082 · +0.061 · +0.062 · -0.040
- by month (trades, R): 2024-10 -1.6 (11) · 2024-11 -3.6 (20) · 2024-12 +1.6 (20) · 2025-01 -3.6 (19) · 2025-02 +4.4 (19) · 2025-03 +0.7 (20) · 2025-04 +2.4 (21) · 2025-05 +3.4 (20) · 2025-06 +0.6 (19) · 2025-07 -2.9 (20) · 2025-08 +0.9 (21) · 2025-09 -3.5 (20) · 2025-10 +1.1 (5)
- sides: short 78 trades -0.119R, long 157 trades +0.060R
- exits: time 140, stop 95
