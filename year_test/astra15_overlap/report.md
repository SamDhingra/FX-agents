# Astra 15 strategies on OANDA data — same dates as Astra's vendor data

Rules: ASTRA-INTRADAY-15-v0.2.0-simple, Astra's own code run unchanged (fxagents/astra15). Costs: Astra's (spread 0.40 / 1.50 / 2.50, slippage 0.10 / 0.375 / 0.625 per fill).
Data: XAUUSD 2026-02-01 → 2026-09-25 (231,595 bars), NDQ 2026-02-01 → 2026-09-25 (232,853 bars), US30 2026-02-01 → 2026-09-25 (232,825 bars). Slices: development ≤ 2026-06-30, validation ≤ 2026-07-31, evaluation ≤ 2026-09-25.

## Headline

**Nothing passes** (pass = ≥100 trades, avg R > 0, 5-session-block 95% range above 0, avg R > 0 at 2× costs).

Astra's shortlist: G-S2 84 trades, avg +0.121R, 95% -0.09 to +0.32, 2× costs +0.047; N-S1 20 trades, avg -0.029R, 95% — to —, 2× costs -0.042; N-S2 67 trades, avg -0.081R, 95% -0.35 to +0.20, 2× costs -0.129; U-S2 58 trades, avg +0.097R, 95% -0.10 to +0.30, 2× costs +0.061.

## All 15 (base costs, volume filter on)

| ID | Trades | Avg R | 95% range | Total R | Avg R 2× costs | Avg R volume off (N) | Avg R dev / val / eval | Astra vendor N / avg R | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| G-S1 | 32 | -0.294 | -0.59 to +0.01 | -9.4 | -0.349 | -0.239 (96) | -0.20 / -0.09 / -0.53 | 21 / -0.244 | too few trades |
| G-S2 ★ | 84 | +0.121 | -0.09 to +0.32 | +10.2 | +0.047 | +0.036 (140) | +0.16 / +0.09 / +0.07 | 58 / +0.097 | too few trades |
| G-S3 | 20 | -0.272 | — | -5.4 | -0.336 | -0.298 (30) | -0.32 / -0.05 / -1.00 | 18 / -0.137 | too few trades |
| G-H1 | 1 | -1.000 | — | -1.0 | -1.000 | -0.683 (5) | -1.00 / — / — | 0 / — | too few trades |
| G-H2 | 40 | -0.084 | -0.35 to +0.19 | -3.4 | -0.109 | +0.070 (75) | +0.13 / +0.04 / -0.45 | 34 / +0.009 | too few trades |
| N-S1 ★ | 20 | -0.029 | — | -0.6 | -0.042 | +0.060 (74) | -0.11 / +0.33 / +0.25 | 20 / +0.345 | too few trades |
| N-S2 ★ | 67 | -0.081 | -0.35 to +0.20 | -5.4 | -0.129 | -0.006 (131) | -0.10 / +0.20 / -0.27 | 46 / +0.211 | too few trades |
| N-S3 | 19 | -0.263 | — | -5.0 | -0.529 | -0.155 (28) | -0.16 / -0.40 / -0.41 | 14 / -0.478 | too few trades |
| N-H1 | 4 | -0.350 | — | -1.4 | -0.354 | -0.366 (7) | -0.35 / — / — | 3 / -0.512 | too few trades |
| N-H2 | 34 | +0.083 | -0.31 to +0.52 | +2.8 | +0.063 | +0.077 (60) | +0.16 / +0.66 / -0.37 | 25 / -0.189 | too few trades |
| U-S1 | 19 | -0.052 | — | -1.0 | -0.026 | -0.139 (47) | +0.02 / +0.28 / -0.38 | 10 / -0.300 | too few trades |
| U-S2 ★ | 58 | +0.097 | -0.10 to +0.30 | +5.6 | +0.061 | -0.051 (104) | -0.02 / +0.58 / +0.17 | 40 / +0.212 | too few trades |
| U-S3 | 24 | -0.157 | — | -3.8 | -0.134 | -0.066 (32) | -0.16 / -0.65 / +0.28 | 21 / -0.167 | too few trades |
| U-H1 | 1 | +0.423 | — | +0.4 | +0.388 | +1.079 (3) | +0.42 / — / — | 1 / +0.398 | too few trades |
| U-H2 | 21 | -0.151 | — | -3.2 | -0.167 | -0.039 (37) | -0.10 / -0.06 / -0.27 | 17 / -0.065 | too few trades |
