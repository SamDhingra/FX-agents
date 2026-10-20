# Pre-registered follow-up — judged once on untouched 2016 → 2020 (frozen efbe1493f311)

Cells: macd_cross:5m@pb-ndq-d — taken unchanged from frozen file data/year_test/playbook_test/cells_frozen.json. Chosen after the playbook test (Oct 20 2026) as the only setup positive in every 2021–2026 piece; it failed step 1 narrowly (95% range touching zero, negative at 2× costs), so this run is a stricter-than-usual check, not a rescue: same engine, same live filters and position manager, real per-minute bid/ask spread, same gates (≥ 100 trades, avg R > 0, 95% day-block range above 0, avg R > 0 at 2× costs, positive in both halves).

| Cell | Verdict | Trades | Win | Avg R | 95% range | 2× costs | 1st half | 2nd half | Spread / risk |
|---|---|---|---|---|---|---|---|---|---|
| macd_cross:5m@pb-ndq-d | **no** | 1020 | 45% | -0.110 | -0.17 to -0.05 | -0.234 | -0.179 | -0.041 | 9% |

By year: 2016 -0.212 (206) · 2017 -0.197 (210) · 2018 -0.196 (187) · 2019 -0.053 (218) · 2020 +0.107 (199)
