"""daily_rsi2_adx2 — Sam's daily trend rule (2026-10-20). Daily candles close 17:00 NY.

Entry (long) at a daily close where  close > SMA(50),  close > EMA(7)  and  RSI(2) > ADX(2);  filled at the next open.
Exit at the first later daily close where RSI(2) < ADX(2);  filled at the next open.

The rule has no stop, but results are measured in R, so a wide protective stop is placed at entry − stop_atr × ATR(14)
(daily). It's there to define 1R and as a disaster stop; at 3 ATR it should rarely be hit before the signal exit.
Change stop_atr and the R numbers rescale; whether the rule makes money doesn't change unless the stop starts firing.
"""
import numpy as np

from fxagents.bt import Costs, Exits, Signal, Strategy, ind


class DailyRsi2Adx2(Strategy):
    name = "daily_rsi2_adx2"
    symbol = "XAUUSD"
    description = "Daily: close above SMA50 and EMA7 with RSI(2) > ADX(2); exit when RSI(2) < ADX(2). Long only."
    params = {"sma": 50, "ema": 7, "rsi": 2, "adx": 2, "stop_atr": 3.0, "use_trend": True, "shorts": False}
    exits = Exits(hold_overnight=True)
    costs = Costs(gap_exit_min=5 * 1440)        # held over weekends and holidays: a market closure isn't an exit
    news_block = None                           # a daily rule doesn't dodge releases
    warmup_days = 200
    variants = {"no_trend_filter": {"use_trend": False}}

    def signals(self, m):
        P = self.params
        b = m.bars("1d")
        c = b.c.to_numpy()
        end = b.end.to_numpy()
        sma, ema = ind.sma(c, P["sma"]), ind.ema(c, P["ema"])
        r, a = ind.rsi(c, P["rsi"]), ind.adx(b, P["adx"])
        atr = ind.atr(b, 14)
        out = []
        sides = (1, -1) if P["shorts"] else (1,)
        for side in sides:
            on = (r > a) if side > 0 else (r < a)          # shorts: the exact mirror (RSI(2) below ADX(2) …)
            off = (r < a) if side > 0 else (r > a)
            trend = (c > sma) & (c > ema) if side > 0 else (c < sma) & (c < ema)
            ok = on & (trend if P["use_trend"] else True) & np.isfinite(atr) & np.isfinite(sma)
            for i in np.flatnonzero(ok):
                later = np.flatnonzero(off[i + 1:])
                exit_t = int(end[i + 1 + later[0]]) if len(later) else None
                out.append(Signal(t=int(end[i]), side=side, stop=float(c[i] - side * P["stop_atr"] * atr[i]),
                                  expire_min=3 * 1440,        # next open can be after a weekend
                                  exit_t=exit_t, tag="trend" if P["use_trend"] else "no_trend",
                                  info={"rsi": float(r[i]), "adx": float(a[i])}))
        return out
