# Chop / trend routing check on 365d_p2

Every research trade except 1m (840,402 trades, each cell's own record), R as sized by Risk. Regime = Choppiness Index (14) of the last completed 15m candle before the signal. Rule fixed beforehand: CHOP ≥ 61.8 → scalps only; CHOP ≤ 38.2 → no scalps; between → anything.

## 1 · What the rule would keep and drop

| | Trades · win · avg R | Total R |
|---|---|---|
| All trades | 840,402 · 41% · -0.110 | -92,611 |
| Kept by the rule | 756,800 · 41% · -0.111 | -84,118 |
| Dropped by the rule | 83,602 · 41% · -0.102 | -8,493 |

**the rule does not help: the trades it drops are no worse than the ones it keeps** (avg -0.111R kept vs -0.102R dropped). A real effect should also show up per instrument in section 3.

## 2 · Exit style × regime (trades · win · avg R)

| Exit | trend (≤38.2) | 38.2–50 | 50–61.8 | chop (≥61.8) |
|---|---|---|---|---|
| scalp | 35,255 · 42% · -0.098 | 112,812 · 40% · -0.113 | 134,995 · 40% · -0.115 | 36,491 · 40% · -0.110 |
| std / tp | 47,035 · 44% · -0.082 | 152,637 · 42% · -0.120 | 170,871 · 42% · -0.114 | 41,524 · 41% · -0.113 |
| trend | 13,985 · 40% · -0.066 | 45,733 · 36% · -0.111 | 42,241 · 35% · -0.101 | 6,823 · 34% · -0.049 |

If the idea is right, scalps should do relatively better on the right (chop) and std/trend exits relatively better on the left (trend).

## 3 · Per instrument: avg R kept vs dropped

| Instrument | Kept | Dropped |
|---|---|---|
| AUDUSD | 120,800 · 33% · -0.227 | 13,279 · 37% · -0.139 |
| EURUSD | 122,172 · 37% · -0.159 | 12,639 · 36% · -0.181 |
| GBPUSD | 124,912 · 35% · -0.220 | 14,246 · 35% · -0.232 |
| NDQ | 124,957 · 46% · -0.036 | 14,067 · 49% · +0.017 |
| US30 | 136,107 · 44% · -0.031 | 15,451 · 43% · -0.042 |
| XAUUSD | 127,852 · 48% · -0.009 | 13,920 · 45% · -0.046 |

Time in each regime (share of trades): mixed 78%, trend 11%, chop 10%.
