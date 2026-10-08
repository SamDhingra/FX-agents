# Audit strategies (ASTRA-*-CFD-001 v0.1.0) — 365 days

History: /app/data/history_365d. Rules exactly as in docs/astra_audit_2026-10-08.md §4; nothing tuned. R per trade after spread + slippage (spread NDQ 1.50 / US30 2.50 / XAUUSD 0.40, slippage max(tick, ¼ spread) per market/stop fill). 95% = bootstrap interval of the average R (at most one trade per day, so trades are day blocks). ×1.5 / ×2 = the same trades with costs scaled.

Warm-up deviation: the spec asks for 500 bars of the longest indicator timeframe; with 365 days the gap test uses ≥ 20 prior daily bars and the others ≥ 150 bars. Instruments are tested separately (no one-index-position rule).

## Summary

| strategy | test | sym | trades | win | avg R | 95% | total R | PF | t | ×1.5 avg | ×2 avg | halves | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ORB-EXP | spec | NDQ | 39 | 31% | -0.302 | -0.63 … +0.08 | -11.8 | 0.55 | -1.66 | -0.310 | -0.318 | +0.02 / -0.61 | fail — average R ≤ 0; 2× costs turn it negative |
| ORB-EXP | spec | US30 | 29 | 34% | -0.155 | -0.56 … +0.33 | -4.5 | 0.75 | -0.68 | -0.166 | -0.183 | -0.48 / +0.15 | too few trades (29) to judge |
| ORB-EXP | control: no W/M or close-location filter | NDQ | 89 | 30% | -0.346 | -0.56 … -0.12 | -30.8 | 0.50 | -3.03 | -0.352 | -0.361 | -0.21 / -0.48 |  |
| ORB-EXP | control: no W/M or close-location filter | US30 | 65 | 26% | -0.331 | -0.61 … -0.03 | -21.5 | 0.53 | -2.20 | -0.327 | -0.340 | -0.10 / -0.56 |  |
| GAP-FAIL | spec | NDQ | 0 | | | | | | | | | | no trades |
| GAP-FAIL | spec | US30 | 0 | | | | | | | | | | no trades |
| GAP-FAIL | control: unconditional small-gap fade | NDQ | 29 | 21% | -0.359 | -0.78 … +0.15 | -10.4 | 0.51 | -1.47 | -0.373 | -0.387 | -0.43 / -0.29 |  |
| GAP-FAIL | control: unconditional small-gap fade | US30 | 34 | 29% | +0.090 | -0.55 … +0.86 | +3.1 | 1.14 | +0.24 | +0.066 | +0.046 | -0.47 / +0.65 |  |
| H1-VOL-TREND | spec | XAUUSD | 43 | 56% | +0.026 | -0.17 … +0.23 | +1.1 | 1.11 | +0.26 | +0.019 | -0.007 | +0.11 / -0.05 | fail — 95% interval includes zero (unproven); 2× costs turn it negative; no better than its control |
| H1-VOL-TREND | spec | NDQ | 57 | 56% | +0.084 | -0.16 … +0.35 | +4.8 | 1.23 | +0.64 | +0.078 | +0.071 | +0.13 / +0.04 | fail — 95% interval includes zero (unproven) |
| H1-VOL-TREND | control: plain 12-bar breakout | XAUUSD | 145 | 43% | -0.099 | -0.22 … +0.03 | -14.4 | 0.73 | -1.54 | -0.106 | -0.117 | -0.05 / -0.14 |  |
| H1-VOL-TREND | control: plain 12-bar breakout | NDQ | 186 | 48% | -0.013 | -0.14 … +0.12 | -2.5 | 0.96 | -0.20 | -0.019 | -0.025 | -0.07 / +0.04 |  |
| H1-VOL-TREND | control: 10:00 entry with the EMA trend | XAUUSD | 234 | 53% | +0.076 | -0.03 … +0.17 | +17.7 | 1.27 | +1.49 | +0.065 | +0.058 | +0.10 / +0.05 | better than spec |
| H1-VOL-TREND | control: 10:00 entry with the EMA trend | NDQ | 234 | 49% | +0.046 | -0.09 … +0.18 | +10.9 | 1.11 | +0.67 | +0.040 | +0.034 | +0.05 / +0.04 |  |

Verdict rule (frozen before the run): PROMISING needs ≥ 30 trades, average R > 0, the 95% interval above zero, average R > 0 at 2× costs, and a better average than its best control. Anything else fails; a positive average with an interval spanning zero is 'unproven', not a pass.

## Detail

### ORB-EXP · NDQ · spec

- 39 trades 2025-10-08 → 2026-10-08, worst drawdown -15.8R
- quarters (avg R): +0.200 · -0.262 · -0.867 · -0.278
- by month (trades, R): 2025-11 -2.0 (2) · 2025-12 -1.0 (1) · 2026-01 +1.9 (5) · 2026-02 +3.2 (2) · 2026-03 -3.0 (7) · 2026-04 -0.6 (4) · 2026-05 -4.0 (4) · 2026-06 -2.6 (4) · 2026-07 -0.9 (3) · 2026-08 -0.8 (2) · 2026-09 +0.3 (3) · 2026-10 -2.0 (2)
- sides: short 18 trades -0.685R, long 21 trades +0.025R
- exits: stop 35, time 4

### ORB-EXP · US30 · spec

- 29 trades 2025-10-08 → 2026-10-08, worst drawdown -8.7R
- quarters (avg R): -0.549 · -0.468 · +0.420 · +0.036
- by month (trades, R): 2025-11 -3.0 (3) · 2025-12 +0.7 (1) · 2026-01 -2.1 (4) · 2026-02 -1.0 (1) · 2026-03 -2.3 (6) · 2026-04 +4.8 (3) · 2026-05 -0.9 (3) · 2026-06 -0.0 (2) · 2026-08 -2.0 (3) · 2026-09 +1.2 (3)
- sides: short 10 trades -0.097R, long 19 trades -0.185R
- exits: stop 24, time 5

### ORB-EXP · NDQ · control: no W/M or close-location filter

- 89 trades 2025-10-08 → 2026-10-08, worst drawdown -31.0R
- quarters (avg R): +0.008 · -0.475 · -0.559 · -0.373
- by month (trades, R): 2025-11 -4.0 (4) · 2025-12 -0.8 (5) · 2026-01 -0.5 (9) · 2026-02 +3.5 (3) · 2026-03 -4.9 (12) · 2026-04 -2.5 (11) · 2026-05 -3.7 (9) · 2026-06 -4.6 (9) · 2026-07 -5.0 (7) · 2026-08 -3.3 (8) · 2026-09 -3.0 (10) · 2026-10 -2.0 (2)
- sides: short 41 trades -0.537R, long 48 trades -0.183R
- exits: stop 82, time 7

### ORB-EXP · US30 · control: no W/M or close-location filter

- 65 trades 2025-10-08 → 2026-10-08, worst drawdown -21.5R
- quarters (avg R): -0.326 · +0.092 · -0.418 · -0.674
- by month (trades, R): 2025-11 -3.0 (3) · 2025-12 +0.4 (3) · 2026-01 -4.1 (6) · 2026-02 +2.1 (4) · 2026-03 -3.9 (10) · 2026-04 +5.9 (10) · 2026-05 -3.9 (6) · 2026-06 -2.3 (5) · 2026-07 -3.0 (3) · 2026-08 -7.0 (8) · 2026-09 -1.8 (6) · 2026-10 -1.0 (1)
- sides: short 28 trades -0.419R, long 37 trades -0.265R
- exits: stop 60, time 5

### GAP-FAIL · NDQ · control: unconditional small-gap fade

- 29 trades 2025-10-08 → 2026-10-08, worst drawdown -13.1R
- quarters (avg R): -0.003 · -0.705 · -0.876 · +0.098
- by month (trades, R): 2025-11 -2.6 (3) · 2025-12 +3.6 (4) · 2026-01 -2.0 (2) · 2026-02 -3.0 (3) · 2026-03 -1.9 (4) · 2026-04 -2.0 (2) · 2026-05 -3.1 (4) · 2026-07 -1.0 (1) · 2026-08 +3.3 (4) · 2026-09 -1.6 (2)
- sides: short 17 trades -0.344R, long 12 trades -0.381R
- exits: stop 20, time 6, target 3

### GAP-FAIL · US30 · control: unconditional small-gap fade

- 34 trades 2025-10-08 → 2026-10-08, worst drawdown -10.4R
- quarters (avg R): -0.255 · -0.484 · +1.515 · -0.301
- by month (trades, R): 2025-11 -0.8 (5) · 2025-12 -1.5 (4) · 2026-01 -3.0 (3) · 2026-02 -1.3 (6) · 2026-03 +8.1 (2) · 2026-04 -1.0 (1) · 2026-05 +5.2 (4) · 2026-06 +0.2 (2) · 2026-08 -1.4 (3) · 2026-09 -0.4 (3) · 2026-10 -1.0 (1)
- sides: short 17 trades +0.221R, long 17 trades -0.041R
- exits: stop 20, time 8, target 6

### H1-VOL-TREND · XAUUSD · spec

- 43 trades 2025-10-08 → 2026-10-08, worst drawdown -2.7R
- quarters (avg R): -0.062 · +0.238 · +0.090 · -0.180
- by month (trades, R): 2025-10 -1.0 (2) · 2025-11 +0.4 (2) · 2025-12 +0.0 (3) · 2026-01 +0.3 (6) · 2026-02 +0.9 (2) · 2026-03 +0.4 (3) · 2026-04 +0.9 (4) · 2026-05 -1.5 (3) · 2026-06 +1.7 (6) · 2026-07 -0.8 (4) · 2026-08 +0.4 (4) · 2026-09 +0.4 (3) · 2026-10 -1.0 (1)
- sides: short 20 trades +0.105R, long 23 trades -0.043R
- exits: time 37, stop 6

### H1-VOL-TREND · NDQ · spec

- 57 trades 2025-10-08 → 2026-10-08, worst drawdown -5.0R
- quarters (avg R): +0.068 · +0.109 · +0.315 · -0.155
- by month (trades, R): 2025-10 +3.0 (4) · 2025-11 +0.1 (4) · 2025-12 -0.5 (2) · 2026-01 -1.5 (4) · 2026-02 -0.4 (5) · 2026-03 +0.2 (5) · 2026-04 +2.2 (6) · 2026-05 -0.5 (7) · 2026-06 +2.5 (3) · 2026-07 -0.1 (5) · 2026-08 -0.8 (6) · 2026-09 +1.7 (4) · 2026-10 -1.1 (2)
- sides: short 23 trades -0.020R, long 34 trades +0.154R
- exits: time 36, stop 21

### H1-VOL-TREND · XAUUSD · control: plain 12-bar breakout

- 145 trades 2025-10-08 → 2026-10-08, worst drawdown -17.9R
- quarters (avg R): -0.180 · +0.104 · -0.131 · -0.188
- by month (trades, R): 2025-10 +1.5 (7) · 2025-11 -2.7 (9) · 2025-12 -6.3 (15) · 2026-01 -0.2 (13) · 2026-02 +2.7 (11) · 2026-03 +1.2 (14) · 2026-04 +2.1 (10) · 2026-05 -4.2 (14) · 2026-06 +0.5 (10) · 2026-07 -4.1 (14) · 2026-08 +1.5 (13) · 2026-09 -4.3 (13) · 2026-10 -2.0 (2)
- sides: short 66 trades +0.002R, long 79 trades -0.184R
- exits: time 112, stop 33

### H1-VOL-TREND · NDQ · control: plain 12-bar breakout

- 186 trades 2025-10-08 → 2026-10-08, worst drawdown -18.8R
- quarters (avg R): -0.102 · -0.033 · +0.116 · -0.032
- by month (trades, R): 2025-10 +5.4 (9) · 2025-11 -1.3 (17) · 2025-12 -8.0 (18) · 2026-01 -5.0 (17) · 2026-02 -0.5 (17) · 2026-03 +3.1 (15) · 2026-04 +2.7 (15) · 2026-05 +0.4 (13) · 2026-06 +0.1 (15) · 2026-07 +4.2 (18) · 2026-08 -5.1 (16) · 2026-09 +2.2 (12) · 2026-10 -0.7 (4)
- sides: short 71 trades -0.072R, long 115 trades +0.023R
- exits: time 119, stop 67

### H1-VOL-TREND · XAUUSD · control: 10:00 entry with the EMA trend

- 234 trades 2025-10-08 → 2026-10-08, worst drawdown -7.7R
- quarters (avg R): +0.085 · +0.107 · -0.022 · +0.132
- by month (trades, R): 2025-10 -0.4 (10) · 2025-11 +5.5 (18) · 2025-12 -1.1 (20) · 2026-01 +1.9 (19) · 2026-02 +1.9 (19) · 2026-03 +3.0 (21) · 2026-04 -0.4 (20) · 2026-05 -5.7 (20) · 2026-06 +4.6 (20) · 2026-07 +3.1 (21) · 2026-08 +1.8 (21) · 2026-09 +3.9 (20) · 2026-10 -0.5 (5)
- sides: short 114 trades +0.150R, long 120 trades +0.005R
- exits: time 189, stop 45

### H1-VOL-TREND · NDQ · control: 10:00 entry with the EMA trend

- 234 trades 2025-10-08 → 2026-10-08, worst drawdown -19.0R
- quarters (avg R): +0.139 · -0.034 · +0.151 · -0.071
- by month (trades, R): 2025-10 +1.3 (10) · 2025-11 +4.7 (18) · 2025-12 +1.1 (20) · 2026-01 +2.3 (19) · 2026-02 -11.5 (19) · 2026-03 -0.4 (21) · 2026-04 +9.9 (20) · 2026-05 +3.1 (20) · 2026-06 +8.6 (20) · 2026-07 -5.8 (21) · 2026-08 -1.5 (21) · 2026-09 -2.5 (20) · 2026-10 +1.6 (5)
- sides: short 95 trades +0.015R, long 139 trades +0.068R
- exits: time 140, stop 94
