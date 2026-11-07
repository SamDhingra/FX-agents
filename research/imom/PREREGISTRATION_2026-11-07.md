# Intraday momentum into the close (rest-of-day → last half-hour): pre-registration (Nov 7, 2026, before any run)

## Why

Every chart-pattern family we tested has about zero edge before costs (trade atlas, Nov 6), and the EMA21 family
closed on Nov 7. This idea works differently: it comes from flows on the daily clock rather than candle shapes.

Baltussen, Da, Lammers & Martens (*Journal of Financial Economics* 2021, "Hedging demand and market intraday momentum")
cover 60+ futures, 1974–2020:
- the return from the previous close to 30 minutes before the close predicts the last half-hour;
- equity index futures: 55% of days right, Sharpe 1.73 before costs, still present in 2000–2020;
- the mechanism is short-gamma hedging near the close.

Zhang & Hua (*Risks* 2024) report that the older first-half-hour and overnight signals weakened on SPY/QQQ, and that
the 15:00–15:30 return still predicted the close in 2022–2024.

What we have already seen in this family, on NDQ only:
- **C10** (morning → afternoon) passed 2021–2026 and was not significant on 2016–2020.
- **Gemini's `ndq_last_hour_gamma_v1`** (filtered, with stop and target): +0.065R, failed overall, but beat its coin
  flip.

**US30 has never been tested in this family**, so it is the primary.

## Rule `imom` (one trade per NY weekday, per instrument)

- **Prices.**
  - Signal prices are 1-minute mid closes.
  - "Price at T" = the close of the last minute starting before T, if that minute started within 3 minutes of T.
  - Otherwise the day is skipped.
- **Signal.** r = price at 15:30 ÷ price at 16:00 on the previous weekday that has data − 1, both NY time.
- **Side.**
  - r > 0: long; r < 0: short; r = 0: no trade.
  - Long buys at the ask, short sells at the bid, on the open of the first minute starting at or after 15:30, within
    3 minutes.
- **Exit.**
  - The close of the last minute starting before 16:00 (normally the 15:59 minute), within 3 minutes.
  - A long sells at its bid, a short buys at its ask.
- **No stop, no target.**
- **Results** are in basis points of the entry price after the real spread, and in points.
  - "2× costs" subtracts one more spread (entry spread + exit spread) ÷ 2.

## Gates (all required)

1. at least 100 trades;
2. the 95% range of mean net bps above 0, resampling 5-trading-day blocks;
3. mean net bps at 2× costs above 0;
4. mean net bps above 0 in both halves;
5. **beats always-long:** the paired difference per day (imom − always long in the same window, both net of spread) has
   a 95% range (same blocks) above 0. Up days alone can't pass this one.
6. **beats a random sign:** each day's sign is taken from another random day's signal (2,000 permutations, seed 7).
   The real mean must beat at least 95% of them (one-sided p < 0.05).

## Stages

| stage | data | split | judged |
|---|---|---|---|
| seen | `holdout_m1` + `dev_m1`, 2021-01-01 → 2026-09-30 | 2023-11-17 | **US30**: decides. **NDQ**: supporting only; C10 and Gemini's rule already used NDQ in this family. |
| vault | `old_m1_idx`, 2016–2020, once | 2018-07-01 | runs only if US30 passed seen. US30 decides; NDQ is shown as information (C10 already used NDQ's vault for this family). |

## What follows

- **US30 passes both:** a paper book `imom_us30` with its own 16:00 exit (the bot flattens at 15:50 today; C10 has its
  own 15:45 exit). Reviewed after 100 forward trades. Nothing on the account.
- **US30 fails seen or vault:** closing-flow momentum on index CFDs is closed. C10 continues unchanged.

## Information (never a pass)

- exit at 15:50 instead of 16:00 (fits today's flatten);
- the Zhang & Hua signal (15:00 → 15:30 return) instead of the rest-of-day return;
- only days with |r| above its running median (earlier days only);
- results by year, long vs short days, and always-long itself;
- gold, with the COMEX close: signal = previous 13:30 → today 13:00, trade 13:00 → 13:30 NY.
