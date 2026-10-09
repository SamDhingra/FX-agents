# Astra 15 strategies on OANDA data — unseen: before Astra's data

Rules: ASTRA-INTRADAY-15-v0.2.0-simple, Astra's own code run unchanged (fxagents/astra15). Costs: Astra's (spread 0.40 / 1.50 / 2.50, slippage 0.10 / 0.375 / 0.625 per fill).
Data: XAUUSD 2024-10-08 → 2026-03-25 (515,534 bars), NDQ 2024-10-08 → 2026-03-25 (514,589 bars), US30 2024-10-08 → 2026-03-25 (513,667 bars). Slices: development ≤ 2025-05-03, validation ≤ 2025-10-13, evaluation ≤ 2026-03-25.

## Headline

**Nothing passes** (pass = ≥100 trades, avg R > 0, 5-session-block 95% range above 0, avg R > 0 at 2× costs).

Astra's shortlist: G-S2 170 trades, avg +0.001R, 95% -0.14 to +0.14, 2× costs -0.130; N-S1 71 trades, avg -0.186R, 95% -0.38 to +0.03, 2× costs -0.222; N-S2 141 trades, avg +0.053R, 95% -0.15 to +0.24, 2× costs -0.017; U-S2 103 trades, avg -0.120R, 95% -0.30 to +0.06, 2× costs -0.157.

## All 15 (base costs, volume filter on)

| ID | Trades | Avg R | 95% range | Total R | Avg R 2× costs | Avg R volume off (N) | Avg R dev / val / eval | Astra vendor N / avg R | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| G-S1 | 77 | +0.022 | -0.21 to +0.26 | +1.7 | -0.066 | +0.046 (182) | -0.11 / +0.15 / +0.10 | 21 / -0.244 | too few trades |
| G-S2 ★ | 170 | +0.001 | -0.14 to +0.14 | +0.2 | -0.130 | -0.026 (263) | +0.06 / +0.00 / -0.04 | 58 / +0.097 | 95% range includes 0 |
| G-S3 | 20 | -0.146 | — | -2.9 | -0.149 | +0.044 (46) | -0.79 / -0.22 / -0.05 | 18 / -0.137 | too few trades |
| G-H1 | 10 | -0.294 | — | -2.9 | -0.189 | -0.217 (18) | -0.70 / -0.01 / -0.27 | 0 / — | too few trades |
| G-H2 | 114 | +0.123 | -0.06 to +0.33 | +14.0 | +0.021 | +0.087 (184) | +0.33 / +0.09 / -0.05 | 34 / +0.009 | 95% range includes 0 |
| N-S1 ★ | 71 | -0.186 | -0.38 to +0.03 | -13.2 | -0.222 | -0.132 (192) | -0.08 / -0.12 / -0.35 | 20 / +0.345 | too few trades |
| N-S2 ★ | 141 | +0.053 | -0.15 to +0.24 | +7.5 | -0.017 | -0.056 (290) | +0.19 / +0.02 / -0.10 | 46 / +0.211 | 95% range includes 0 |
| N-S3 | 48 | -0.116 | -0.42 to +0.25 | -5.5 | -0.221 | -0.052 (69) | +0.20 / -0.14 / -0.30 | 14 / -0.478 | too few trades |
| N-H1 | 6 | -0.201 | — | -1.2 | -0.206 | -0.205 (14) | +0.79 / -1.00 / -0.25 | 3 / -0.512 | too few trades |
| N-H2 | 88 | -0.189 | -0.36 to -0.00 | -16.6 | -0.210 | -0.137 (150) | -0.08 / -0.26 / -0.25 | 25 / -0.189 | too few trades |
| U-S1 | 54 | +0.062 | -0.17 to +0.32 | +3.3 | +0.071 | +0.018 (125) | -0.05 / -0.10 / +0.32 | 10 / -0.300 | too few trades |
| U-S2 ★ | 103 | -0.120 | -0.30 to +0.06 | -12.3 | -0.157 | -0.103 (196) | -0.01 / -0.09 / -0.23 | 40 / +0.212 | avg R ≤ 0 |
| U-S3 | 49 | +0.159 | -0.20 to +0.50 | +7.8 | +0.546 | +0.131 (87) | -0.58 / -0.01 / +0.66 | 21 / -0.167 | too few trades |
| U-H1 | 5 | +0.054 | — | +0.3 | +0.050 | +0.348 (9) | +0.61 / — / -0.78 | 1 / +0.398 | too few trades |
| U-H2 | 47 | -0.227 | -0.52 to +0.08 | -10.7 | -0.246 | -0.217 (83) | +0.08 / -0.33 / -0.59 | 17 / -0.065 | too few trades |
