# Jev grade vs trade results

Gate now: advisory · min quality 0.5 · min confidence 0.5 · advisory floor 0.0

R per trade in units of its own risk. Buckets with a handful of trades are noise.

## Real book (hourly_pick)

23 closed trades with a Jev grade · 48% win · avg -0.121R · total -2.8R · sources: jev 23

**By quality** — rank correlation with the result: +0.18 (top half -0.128R over 11, bottom half -0.115R over 12)

| quality | trades | win | avg R | total R |
|---|---|---|---|---|
| 0.3–0.4 | 1 | 100% | +0.261 | +0.3 |
| 0.4–0.5 | 4 | 25% | -0.645 | -2.6 |
| 0.5–0.6 | 9 | 56% | +0.072 | +0.6 |
| 0.6–0.7 | 9 | 44% | -0.124 | -1.1 |

**By confidence** — rank correlation with the result: -0.18 (top half -0.074R over 11, bottom half -0.165R over 12)

| confidence | trades | win | avg R | total R |
|---|---|---|---|---|
| 0.0–0.3 | 5 | 60% | +0.266 | +1.3 |
| 0.3–0.4 | 11 | 36% | -0.351 | -3.9 |
| 0.4–0.5 | 6 | 50% | -0.087 | -0.5 |
| 0.5–0.6 | 1 | 100% | +0.261 | +0.3 |

**What if the gate had been stricter** (keep only trades at or above both thresholds)

| quality ≥ | confidence ≥ | trades kept | win | avg R | total R |
|---|---|---|---|---|---|
| 0.0 | 0.0 | 23 | 48% | -0.121 | -2.8 |
| 0.0 | 0.4 | 7 | 57% | -0.038 | -0.3 |
| 0.0 | 0.5 | 1 | 100% | +0.261 | +0.3 |
| 0.3 | 0.0 | 23 | 48% | -0.121 | -2.8 |
| 0.3 | 0.4 | 7 | 57% | -0.038 | -0.3 |
| 0.3 | 0.5 | 1 | 100% | +0.261 | +0.3 |
| 0.4 | 0.0 | 22 | 45% | -0.139 | -3.1 |
| 0.4 | 0.4 | 6 | 50% | -0.087 | -0.5 |
| 0.5 | 0.0 | 18 | 50% | -0.026 | -0.5 |
| 0.5 | 0.4 | 3 | 100% | +0.842 | +2.5 |
| 0.6 | 0.0 | 9 | 44% | -0.124 | -1.1 |
| 0.6 | 0.4 | 1 | 100% | +0.751 | +0.8 |

**By instrument** (quality top half vs bottom half, avg R)

- NDQ: 6 trades · top +1.059R · bottom -0.089R
- US30: 6 trades · top +0.156R · bottom -1.018R
- XAUUSD: 11 trades · top -0.178R · bottom -0.371R

## Shadow book (playbook)

12 closed trades with a Jev grade · 67% win · avg +0.202R · total +2.4R · sources: jev 12

**By quality** — rank correlation with the result: +0.21 (top half +0.292R over 6, bottom half +0.113R over 6)

| quality | trades | win | avg R | total R |
|---|---|---|---|---|
| 0.4–0.5 | 1 | 100% | +0.518 | +0.5 |
| 0.5–0.6 | 5 | 60% | +0.032 | +0.2 |
| 0.6–0.7 | 4 | 75% | +0.391 | +1.6 |
| 0.7–1.0 | 2 | 50% | +0.094 | +0.2 |

**By confidence** — rank correlation with the result: +0.27 (top half -0.015R over 6, bottom half +0.419R over 6)

| confidence | trades | win | avg R | total R |
|---|---|---|---|---|
| 0.0–0.3 | 1 | 100% | +0.481 | +0.5 |
| 0.3–0.4 | 6 | 67% | +0.173 | +1.0 |
| 0.4–0.5 | 2 | 0% | -1.000 | -2.0 |
| 0.5–0.6 | 3 | 100% | +0.971 | +2.9 |

**What if the gate had been stricter** (keep only trades at or above both thresholds)

| quality ≥ | confidence ≥ | trades kept | win | avg R | total R |
|---|---|---|---|---|---|
| 0.0 | 0.0 | 12 | 67% | +0.202 | +2.4 |
| 0.0 | 0.4 | 5 | 60% | +0.183 | +0.9 |
| 0.0 | 0.5 | 3 | 100% | +0.971 | +2.9 |
| 0.3 | 0.0 | 12 | 67% | +0.202 | +2.4 |
| 0.3 | 0.4 | 5 | 60% | +0.183 | +0.9 |
| 0.3 | 0.5 | 3 | 100% | +0.971 | +2.9 |
| 0.4 | 0.0 | 12 | 67% | +0.202 | +2.4 |
| 0.4 | 0.4 | 5 | 60% | +0.183 | +0.9 |
| 0.4 | 0.5 | 3 | 100% | +0.971 | +2.9 |
| 0.5 | 0.0 | 11 | 64% | +0.174 | +1.9 |
| 0.5 | 0.4 | 5 | 60% | +0.183 | +0.9 |
| 0.5 | 0.5 | 3 | 100% | +0.971 | +2.9 |
| 0.6 | 0.0 | 6 | 67% | +0.292 | +1.8 |
| 0.6 | 0.4 | 4 | 50% | -0.061 | -0.2 |
| 0.6 | 0.5 | 2 | 100% | +0.877 | +1.8 |
| 0.7 | 0.0 | 2 | 50% | +0.094 | +0.2 |
| 0.7 | 0.4 | 2 | 50% | +0.094 | +0.2 |
| 0.7 | 0.5 | 1 | 100% | +1.187 | +1.2 |

## Shadow book (setup_first)

35 closed trades with a Jev grade · 40% win · avg -0.289R · total -10.1R · sources: jev 35

**By quality** — rank correlation with the result: +0.04 (top half -0.303R over 17, bottom half -0.277R over 18)

| quality | trades | win | avg R | total R |
|---|---|---|---|---|
| 0.0–0.3 | 1 | 100% | +1.188 | +1.2 |
| 0.3–0.4 | 5 | 40% | -0.453 | -2.3 |
| 0.4–0.5 | 9 | 33% | -0.268 | -2.4 |
| 0.5–0.6 | 15 | 33% | -0.486 | -7.3 |
| 0.6–0.7 | 5 | 60% | +0.132 | +0.7 |

**By confidence** — rank correlation with the result: -0.16 (top half -0.459R over 15, bottom half -0.162R over 20)

| confidence | trades | win | avg R | total R |
|---|---|---|---|---|
| 0.0–0.3 | 9 | 56% | +0.215 | +1.9 |
| 0.3–0.4 | 6 | 17% | -0.748 | -4.5 |
| 0.4–0.5 | 11 | 36% | -0.480 | -5.3 |
| 0.5–0.6 | 6 | 50% | -0.247 | -1.5 |
| 0.6–0.7 | 1 | 0% | -1.000 | -1.0 |
| 0.7–1.0 | 2 | 50% | +0.094 | +0.2 |

**What if the gate had been stricter** (keep only trades at or above both thresholds)

| quality ≥ | confidence ≥ | trades kept | win | avg R | total R |
|---|---|---|---|---|---|
| 0.0 | 0.0 | 35 | 40% | -0.289 | -10.1 |
| 0.0 | 0.4 | 20 | 40% | -0.379 | -7.6 |
| 0.0 | 0.5 | 9 | 44% | -0.255 | -2.3 |
| 0.0 | 0.6 | 3 | 33% | -0.271 | -0.8 |
| 0.3 | 0.0 | 34 | 38% | -0.333 | -11.3 |
| 0.3 | 0.4 | 19 | 37% | -0.461 | -8.8 |
| 0.3 | 0.5 | 8 | 38% | -0.435 | -3.5 |
| 0.3 | 0.6 | 2 | 0% | -1.000 | -2.0 |
| 0.4 | 0.0 | 29 | 38% | -0.312 | -9.1 |
| 0.4 | 0.4 | 14 | 36% | -0.464 | -6.5 |
| 0.4 | 0.5 | 4 | 50% | -0.203 | -0.8 |
| 0.5 | 0.0 | 20 | 40% | -0.332 | -6.6 |
| 0.5 | 0.4 | 12 | 42% | -0.375 | -4.5 |
| 0.5 | 0.5 | 3 | 67% | +0.063 | +0.2 |
| 0.6 | 0.0 | 5 | 60% | +0.132 | +0.7 |
| 0.6 | 0.4 | 2 | 50% | -0.344 | -0.7 |

**By instrument** (quality top half vs bottom half, avg R)

- NDQ: 16 trades · top -0.288R · bottom -0.163R
- US30: 6 trades · top -0.058R · bottom +0.248R
- XAUUSD: 13 trades · top -0.393R · bottom -0.694R

## All books together

70 closed trades with a Jev grade · 47% win · avg -0.150R · total -10.5R · sources: jev 70

**By quality** — rank correlation with the result: +0.13 (top half +0.016R over 35, bottom half -0.316R over 35)

| quality | trades | win | avg R | total R |
|---|---|---|---|---|
| 0.0–0.3 | 1 | 100% | +1.188 | +1.2 |
| 0.3–0.4 | 6 | 50% | -0.334 | -2.0 |
| 0.4–0.5 | 14 | 36% | -0.320 | -4.5 |
| 0.5–0.6 | 29 | 45% | -0.224 | -6.5 |
| 0.6–0.7 | 18 | 56% | +0.061 | +1.1 |
| 0.7–1.0 | 2 | 50% | +0.094 | +0.2 |

**By confidence** — rank correlation with the result: -0.06 (top half -0.240R over 33, bottom half -0.069R over 37)

| confidence | trades | win | avg R | total R |
|---|---|---|---|---|
| 0.0–0.3 | 15 | 60% | +0.250 | +3.7 |
| 0.3–0.4 | 23 | 39% | -0.318 | -7.3 |
| 0.4–0.5 | 19 | 37% | -0.411 | -7.8 |
| 0.5–0.6 | 10 | 70% | +0.169 | +1.7 |
| 0.6–0.7 | 1 | 0% | -1.000 | -1.0 |
| 0.7–1.0 | 2 | 50% | +0.094 | +0.2 |

**What if the gate had been stricter** (keep only trades at or above both thresholds)

| quality ≥ | confidence ≥ | trades kept | win | avg R | total R |
|---|---|---|---|---|---|
| 0.0 | 0.0 | 70 | 47% | -0.150 | -10.5 |
| 0.0 | 0.4 | 32 | 47% | -0.216 | -6.9 |
| 0.0 | 0.5 | 13 | 62% | +0.068 | +0.9 |
| 0.0 | 0.6 | 3 | 33% | -0.271 | -0.8 |
| 0.3 | 0.0 | 69 | 46% | -0.169 | -11.7 |
| 0.3 | 0.4 | 31 | 45% | -0.262 | -8.1 |
| 0.3 | 0.5 | 12 | 58% | -0.026 | -0.3 |
| 0.3 | 0.6 | 2 | 0% | -1.000 | -2.0 |
| 0.4 | 0.0 | 63 | 46% | -0.154 | -9.7 |
| 0.4 | 0.4 | 25 | 44% | -0.244 | -6.1 |
| 0.4 | 0.5 | 7 | 71% | +0.300 | +2.1 |
| 0.5 | 0.0 | 49 | 49% | -0.106 | -5.2 |
| 0.5 | 0.4 | 20 | 55% | -0.053 | -1.1 |
| 0.5 | 0.5 | 6 | 83% | +0.517 | +3.1 |
| 0.6 | 0.0 | 20 | 55% | +0.065 | +1.3 |
| 0.6 | 0.4 | 7 | 57% | -0.026 | -0.2 |
| 0.6 | 0.5 | 2 | 100% | +0.877 | +1.8 |
| 0.7 | 0.0 | 2 | 50% | +0.094 | +0.2 |
| 0.7 | 0.4 | 2 | 50% | +0.094 | +0.2 |
| 0.7 | 0.5 | 1 | 100% | +1.187 | +1.2 |

**By instrument** (quality top half vs bottom half, avg R)

- NDQ: 22 trades · top -0.161R · bottom +0.109R
- US30: 12 trades · top -0.204R · bottom -0.132R
- XAUUSD: 36 trades · top +0.092R · bottom -0.531R
