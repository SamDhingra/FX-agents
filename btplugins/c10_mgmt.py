"""c10_mgmt — C10 v2's entries (unchanged) with Sam's trade-management ideas as mechanical rules (Oct 21 2026).

Same signals, same stop, same 15:45 exit as gpt_c10_afternoon_continuation_v2. Only the management changes, chosen by
`mgmt`; the report's variant lines show every rule side by side on the same entries (base = "none" = C10 v2 as tested):
  none           2R target, nothing else (= C10 v2)
  cut30 / cut60  out at the next minute if the trade isn't above 0R after 30 / 60 minutes ("not working → cut it")
  be1            stop to entry + 0.1R once +1R is reached
  part1          half off at +1R, stop to +0.1R, rest to the 2R target (the bot's own live rule)
  trail          no target: once +1R, trail the stop 1R behind the best price ("let it run, trail it")
  thesis_open    out when a 15-minute close goes back through today's 09:30 open (the morning move is undone)
  thesis_prev    out when a 15-minute close goes back through yesterday's close (the day's direction has flipped)
  cut30_trail    cut30 + trail
"Out" for the thesis rules = the stop is pulled to just behind the current price, so it fills within a minute or two
(the engine only lets a strategy tighten its stop). Adding to winners isn't modelled (the engine has no adds).
Each rule is a separate try on the same data — a winner here still has to stand up in the vault and on paper.
"""
import numpy as np

from fxagents.bt import Costs, Exits, Signal, Strategy, ind

MIN_STOP = {}                       # v2: no fixed-point minimum; the spread filter below does that job at any price


def _bars(m, tf):
    b = m.bars(tf)
    t = b.index
    return (b, b.o.to_numpy(), b.h.to_numpy(), b.l.to_numpy(), b.c.to_numpy(), b.end.to_numpy(),
            (t.hour * 60 + t.minute).to_numpy(), np.asarray([d.toordinal() for d in t.date]), t.dayofweek.to_numpy())


def _sig(m, t, side, ref, stop, atr, tag, **kw):
    """GPT's risk filters: stop 0.5–2.5 ATR, at least the friction minimum, at most 10% of price (checked at the fill)."""
    lo = max(0.5 * atr, MIN_STOP.get(m.symbol, 0.0))
    hi = min(2.5 * atr, 0.10 * ref)
    if not (np.isfinite(stop) and np.isfinite(atr)) or lo > hi:
        return None
    return Signal(t=int(t), side=side, stop=float(stop), risk_min=float(lo), risk_max=float(hi), tag=tag, **kw)


MGMT = {
    "none": {},
    "cut30": {"time_stop": (30, 0.0)},
    "cut60": {"time_stop": (60, 0.0)},
    "be1": {"be_at_r": 1.0, "be_lock_r": 0.1},
    "part1": {"partials": [(1.0, 0.5, 0.1)]},
    "trail": {"target_r": None, "trail": {"kind": "gap_r", "gap": 1.0}, "trail_after_r": 1.0},
    "thesis_open": {}, "thesis_prev": {},
    "cut30_trail": {"time_stop": (30, 0.0), "target_r": None, "trail": {"kind": "gap_r", "gap": 1.0}, "trail_after_r": 1.0},
}


class C10Mgmt(Strategy):
    name = "c10_mgmt"
    family = "gpt_c10_afternoon_continuation"   # same entries as C10: its vault is spent
    symbol = "NDQ"
    description = "C10 v2 entries with trade-management rules (cut if not working, breakeven, partial, trail, thesis exits)."
    params = {"move_atr": 1.0, "er_n": 12, "er_min": 0.40, "stop_atr": 1.25, "mgmt": "none"}
    exits = Exits(target_r=2.0, flat_at=945)
    costs = Costs(max_spread_frac=0.10 / 1.3)          # actual spread × 1.3 <= 10% of the stop
    entry_windows = [(780, 781)]
    max_per_day = 1
    news_block = None
    variants = {k: {"mgmt": k} for k in MGMT if k != "none"}

    def signals(self, m):
        P = self.params
        b, o, h, l, c, end, mod, day, dow = _bars(m, 15)
        a = ind.atr(b, 14)
        er = ind.efficiency_ratio(c, P["er_n"])
        pos = {(d, t): i for i, (d, t) in enumerate(zip(day, mod))}
        days = sorted({int(d) for d, w in zip(day, dow) if w < 5})
        out = []
        for prev, d in zip(days, days[1:]):
            ip, i0, i10, i13 = pos.get((prev, 945)), pos.get((d, 570)), pos.get((d, 585)), pos.get((d, 765))
            if None in (ip, i0, i10, i13) or i13 - i0 != 13 or i0 < 100 or not (np.isfinite(a[i13]) and np.isfinite(er[i13])):
                continue
            r10, r13 = c[i10] - c[ip], c[i13] - c[ip]
            if r10 == 0 or np.sign(r10) != np.sign(r13):
                continue
            side = 1 if r13 > 0 else -1
            if side * (c[i13] - o[i0]) < P["move_atr"] * a[i13] or er[i13] < P["er_min"]:
                continue
            s = _sig(m, end[i13], side, c[i13], c[i13] - side * P["stop_atr"] * a[i13], a[i13], "long" if side > 0 else "short",
                     exits=MGMT[P["mgmt"]] or None, info={"open_0930": float(o[i0]), "prev_close": float(c[ip])})
            if s:
                out.append(s)
        return out

    def adjust(self, trade, m, k):
        """thesis_open / thesis_prev: on each completed 15-minute candle, if its close is back through the reference
        level, pull the stop to just behind the current price (an exit within a minute or two)."""
        mg = self.params["mgmt"]
        if mg not in ("thesis_open", "thesis_prev") or (m.mod[k] + 1) % 15:
            return None
        side, ref = trade["side"], trade["signal"].info["open_0930" if mg == "thesis_open" else "prev_close"]
        if side * (m.c[k] - ref) >= 0:
            return None
        return float(m.c[k] - side * max(m.spread[k], 1e-9))
