"""ps1_pullback_reclaim — PS-1.0, "NDQ one-minute pullback reclaim" (Scalping research, Oct 21 2026), ported as written.

Its own evidence was one New York session (4 trades). Here: 2021 → Sep 2026 on OANDA's real 1-minute bid/ask.
  Context: completed 5-minute candles, EMA20 and EMA50 of closes; long when EMA20 > EMA50 and EMA20 > its value three
    completed 5-minute candles earlier (shorts mirror). A 5-minute candle counts only once it has ended.
  Trigger (completed 1-minute mid candles): previous close ≤ its EMA9, this close > its EMA9 and > this open (long).
  Stop: lowest low of this candle and the two before − 0.1 × the previous 1-minute ATR(14), rounded outward to 0.1;
    shorts: highest high + buffer.
  Entry at the next minute's open (bid/ask). Skipped if the stop is not beyond the fill, if it is > 1.5 × the completed
    5-minute ATR(14), or if the friction estimate (spread + 0.5 × spread slippage allowance = 1.5 × the fill's actual
    spread) exceeds 15% of it — i.e. spread > 10% of the stop.
  Exit: full 1R target, the stop, or after 12 minutes. No partials, breakeven, adds.
  Fills 09:35–11:30 and 13:00–15:15 New York; 3 minutes after an exit before the next; at most 6 a day; one at a time.
  No news blackout (the spec omits the app's news gate; a news-filtered version would be a separate experiment).
Variant (control, not a candidate): no_context — the same trigger without the 5-minute trend filter (both directions).
"""
import numpy as np

from fxagents.bt import Costs, Exits, Signal, Strategy, ind


class Ps1PullbackReclaim(Strategy):
    name = "ps1_pullback_reclaim"
    symbol = "NDQ"
    description = "5m EMA20>EMA50 rising → 1m close reclaims EMA9 → 3-bar stop, 1R, max 12 minutes, 09:35–11:30 / 13:00–15:15."
    params = {"ema_fast": 20, "ema_slow": 50, "slope": 3, "ema1": 9, "buf_atr": 0.10, "stop_cap_atr5": 1.5,
              "tick": 0.1, "context": True}
    exits = Exits(target_r=1.0, max_hold_min=12, flat_at=950)
    costs = Costs(max_spread_frac=0.10)            # 1.5 × spread ≤ 15% of the stop
    entry_windows = [(575, 690), (780, 915)]
    max_per_day = 6
    cooldown_min = 3
    news_block = None
    warmup_days = 10
    variants = {"no_context": {"context": False}}

    def signals(self, m):
        P = self.params
        b1 = m.bars(1)
        o, h, l, c, end1 = (b1[k].to_numpy() for k in ("o", "h", "l", "c", "end"))
        e9 = ind.ema(c, P["ema1"])
        a1 = ind.atr(b1, 14)
        b5 = m.bars(5)
        c5, end5 = b5.c.to_numpy(), b5.end.to_numpy()
        f5, s5 = ind.ema(c5, P["ema_fast"]), ind.ema(c5, P["ema_slow"])
        a5 = ind.atr(b5, 14)
        k = np.searchsorted(end5, end1, side="right") - 1            # last completed 5-minute candle at each 1m close
        ok5 = k >= P["slope"]
        kk = np.where(ok5, k, P["slope"])
        up = ok5 & (f5[kk] > s5[kk]) & (f5[kk] > f5[kk - P["slope"]])
        dn = ok5 & (f5[kk] < s5[kk]) & (f5[kk] < f5[kk - P["slope"]])
        prev_c, prev_e = np.r_[np.nan, c[:-1]], np.r_[np.nan, e9[:-1]]
        long_t = (prev_c <= prev_e) & (c > e9) & (c > o)
        short_t = (prev_c >= prev_e) & (c < e9) & (c < o)
        if P["context"]:
            long_t &= up
            short_t &= dn
        t = b1.index
        mod = (t.hour * 60 + t.minute).to_numpy() + 1                # the minute the candle closes
        win = ((mod >= 575) & (mod < 690)) | ((mod >= 780) & (mod < 915))
        q = P["tick"]
        out = []
        for i in np.flatnonzero((long_t | short_t) & win):
            if i < 3 or not (np.isfinite(a1[i - 1]) and np.isfinite(a5[kk[i]])):
                continue
            side = 1 if long_t[i] else -1
            buf = P["buf_atr"] * a1[i - 1]
            if side > 0:
                stop = np.floor((l[i - 2:i + 1].min() - buf) / q) * q
            else:
                stop = np.ceil((h[i - 2:i + 1].max() + buf) / q) * q
            out.append(Signal(t=int(end1[i]), side=side, stop=float(stop), risk_max=float(P["stop_cap_atr5"] * a5[kk[i]]),
                              tag="long" if side > 0 else "short"))
        return out
