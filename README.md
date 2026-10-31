# Market candles (XAUUSD, NDQ, US30)

Refreshed every few minutes. Last refresh: **2026-10-31 22:21:46** (UTC). GitHub caches raw links for up to ~5 minutes, so the
newest candle can be that much behind. Latest prices: [latest.json](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/latest.json)

## Files (CSV, oldest first)
- XAUUSD: [M1](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/XAUUSD_M1.csv), [M5](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/XAUUSD_M5.csv), [M15](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/XAUUSD_M15.csv), [H1](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/XAUUSD_H1.csv), [H4](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/XAUUSD_H4.csv), [D](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/XAUUSD_D.csv)
- NDQ: [M1](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/NDQ_M1.csv), [M5](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/NDQ_M5.csv), [M15](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/NDQ_M15.csv), [H1](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/NDQ_H1.csv), [H4](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/NDQ_H4.csv), [D](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/NDQ_D.csv)
- US30: [M1](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/US30_M1.csv), [M5](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/US30_M5.csv), [M15](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/US30_M15.csv), [H1](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/US30_H1.csv), [H4](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/US30_H4.csv), [D](https://raw.githubusercontent.com/SamDhingra/FX-agents/candles/US30_D.csv)

Columns: `time` = UTC candle OPEN time · `open high low close` = MID price (halfway between bid and ask) ·
`volume` = OANDA tick count (price updates), not traded volume · `complete` = false for the candle still forming (the last row).

Notes
- Source: OANDA practice account v20 API, CFD prices (not futures). Gold = XAU_USD (USD per oz), NDQ = NAS100_USD,
  US30 = US30_USD (index points).
- Candles per file: M1 1440 · M5 1152 · M15 1000 · H1 1000 · H4 600 · D 500.
- H4 and D candles are aligned to 17:00 New York (OANDA's default): the D candle runs 17:00 → 17:00 New York.
- These are mid prices. Real trades pay the spread (gold about 0.5–0.7 points, NDQ about 2–2.5, US30 about 3) on top.
