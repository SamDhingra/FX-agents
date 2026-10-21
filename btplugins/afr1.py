"""afr1 — NDQ Afternoon Failed Reversal, AFR-1 v1.0 (spec of Oct 21 2026), ported as specified. Retrospective only.

Context (C10's, unchanged — fxagents/agents/c10_trader.c10_signal at f0b59ad): at 13:00 New York, d = sign(C13 − P);
sign(C10 − P) = d ≠ 0; d × (C13 − O) ≥ ATR15(14); ER(12) ≥ 0.40; the fourteen 09:30–12:45 candles present; ≥ 120
fifteen-minute candles of history. P = previous weekday's 15:45-candle close, O = 09:30 open (15-minute mid candles).

Trigger (completed 5-minute mid candles closing 13:05 … 14:00), first one that passes every admission check:
  reference L / H = lowest low / highest high of the three candles before j (consecutive); A5 = Wilder ATR(14) of 5-minute
  candles through j−1; b = max(tick, 0.10 × A5).
  long day: low[j] ≤ L − b, close[j] > L, close[j] > open[j], close[j] > O and > P; stop = lowest BID of candle j − b.
  short day: the mirror; stop = highest ASK of candle j + b.
  A 5-minute close through O or P against d before an entry disables the day (no re-arm).
Admission at the fill (the next minute's open, as every result here): its mid still beyond L/H and O/P; s = ask − bid,
  u = max(tick, 0.25 s), worst entry Eb = ask + u (long) / bid − u; D = |Eb − stop| > 0 with the stop beyond the exit
  quote; D ≤ 1.25 × ATR15; (s + 2u) / D ≤ 0.10. Failing candidates are logged and a later candle may still qualify.
Skips: a scheduled FOMC / CPI / NFP / PPI release from 15 minutes before the entry through 15:45 (in practice: FOMC days;
  the morning releases are before the window) — the calendar (fxagents/usd_calendar.py) covers 2021 onward only, so
  2016–2020 runs have NO event filter; NYSE early-close days (Jul 3, Dec 24, the day after Thanksgiving).
Exits: target 2R from the fill, the stop, or 15:45. No partials, adds, breakeven, trailing or Jev.
Attribution variants (spec §10; not candidates to pick from): c10_stop = the AFR entry with C10's 1.25 × ATR15 stop
  from the trigger close; c10_matched = C10 at 13:00 with AFR's event, early-close and cost admission.
The original C10 v2 report is the fourth comparison. The Jev book is forward-only (an LLM reading historical NDQ
afternoons may know what came next), so it is not here.
The report adds net R per ELIGIBLE day (days the 13:00 context armed; 0 on days without a trade) and the matched
day-by-day difference AFR − c10_matched, with a week-block bootstrap.
"""
from collections import Counter
from datetime import date, timedelta

import numpy as np
import pandas as pd

from fxagents.bt import Exits, Signal, Strategy, ind
from fxagents.usd_calendar import events

NS_MIN = 60 * 10 ** 9


def early_close(d: date) -> bool:
    """NYSE 13:00 closes: July 3, December 24 (weekdays) and the day after Thanksgiving."""
    if d.weekday() >= 5:
        return False
    if (d.month, d.day) in ((7, 3), (12, 24)):
        return True
    if d.month == 11 and d.weekday() == 4:
        first = date(d.year, 11, 1)
        thanks = first + timedelta(days=(3 - first.weekday()) % 7 + 21)
        return d == thanks + timedelta(days=1)
    return False


def trigger(side, o, h, l, c, ref_lo, ref_hi, b, O, P) -> bool:
    """The failed-reversal candle (spec §5), mid prices."""
    if side > 0:
        return l <= ref_lo - b and c > ref_lo and c > o and c > O and c > P
    return h >= ref_hi + b and c < ref_hi and c < o and c < O and c < P


def contexts(m, er_n=12, er_min=0.40, move_atr=1.0):
    """{NY date ordinal: dict(side, P, O, C13, A15, t13)} — C10's 13:00 rule, exactly as c10_signal computes it."""
    b = m.bars(15)
    t = b.index
    mod = (t.hour * 60 + t.minute).to_numpy()
    day = np.asarray([d.toordinal() for d in t.date])
    dow = t.dayofweek.to_numpy()
    o, c, end = b.o.to_numpy(), b.c.to_numpy(), b.end.to_numpy()
    a = ind.atr(b, 14)
    er = ind.efficiency_ratio(c, er_n)
    pos = {(d, x): i for i, (d, x) in enumerate(zip(day, mod))}
    with945 = sorted({int(d) for d, w, x in zip(day, dow, mod) if w < 5 and x == 945})
    out = {}
    for d in sorted({int(x) for x, w in zip(day, dow) if w < 5}):
        i13 = pos.get((d, 765))
        if i13 is None or i13 < 119:
            continue
        k = int(np.searchsorted(with945, d)) - 1
        if k < 0:
            continue
        ip, i0, i10 = pos[(with945[k], 945)], pos.get((d, 570)), pos.get((d, 585))
        if i0 is None or i10 is None or i13 - i0 != 13 or not (np.isfinite(a[i13]) and np.isfinite(er[i13])):
            continue
        r10, r13 = c[i10] - c[ip], c[i13] - c[ip]
        if r10 == 0 or np.sign(r10) != np.sign(r13):
            continue
        side = 1 if r13 > 0 else -1
        if side * (c[i13] - o[i0]) < move_atr * a[i13] or er[i13] < er_min:
            continue
        out[d] = {"side": side, "P": float(c[ip]), "O": float(o[i0]), "C13": float(c[i13]), "A15": float(a[i13]),
                  "t13": int(end[i13])}
    return out


class Afr1(Strategy):
    name = "afr1"
    symbol = "NDQ"
    description = "C10's 13:00 context, then a failed countertrend 5m sweep that reclaims (13:05–14:00) → 2R, out 15:45."
    params = {"mode": "afr", "tick": 0.1, "b_frac": 0.10, "u_frac": 0.25, "stop_cap": 1.25, "cost_max": 0.10,
              "first_close": 785, "last_close": 840}
    exits = Exits(target_r=2.0, flat_at=945)
    entry_windows = [(780, 841)]
    max_per_day = 1
    news_block = None                       # handled in signals(): the spec's window runs from entry − 15 min to 15:45
    variants = {"c10_stop": {"mode": "afr_c10stop"}, "c10_matched": {"mode": "c10_matched"}}

    # ── helpers ──
    def _quote(self, m, t_ns):
        """The fill minute (the engine fills market orders at the next minute's open): (bid, ask) or None."""
        k = int(np.searchsorted(m.ns, t_ns))
        if k >= len(m.ns) or m.ns[k] - t_ns > 5 * NS_MIN:
            return None
        return float(m.bid_o[k]), float(m.ask_o[k])

    def _admit(self, m, t_ns, side, stop, a15, cap, beyond):
        """Spec §6 at the fill. None = admitted, else the reason. Data that ends before the fill (the look-ahead audit's
        truncated runs) admits: these are broker-side checks made with the fill's own quote."""
        P = self.params
        q = self._quote(m, t_ns)
        if q is None:
            return None
        bid, ask = q
        mid = (bid + ask) / 2
        if beyond is not None and not beyond(mid):
            return "next quote back on the wrong side of the reference / the morning levels"
        s = ask - bid
        u = max(P["tick"], P["u_frac"] * s)
        eb = ask + u if side > 0 else bid - u
        D = side * (eb - stop)
        if D <= 0 or (side > 0 and stop >= bid) or (side < 0 and stop <= ask):
            return "stop not beyond the executable exit quote"
        if cap and D > P["stop_cap"] * a15:
            return f"stop too far (> {P['stop_cap']:g} × ATR15)"
        if (s + 2 * u) / D > P["cost_max"]:
            return f"friction > {P['cost_max']:.0%} of the stop"
        return None

    def _event(self, d: date, entry_mod: int, ev) -> bool:
        return any(entry_mod - 15 <= minute <= 945 for minute, _ in ev.get(d.isoformat(), []))

    # ── signals ──
    def signals(self, m):
        P = self.params
        ctx = contexts(m)
        ev = events()
        self.diag = {"eligible_days": sorted(ctx), "rejections": Counter()}
        rej = self.diag["rejections"]
        out = []
        if P["mode"] == "c10_matched":
            for d, x in ctx.items():
                dd = date.fromordinal(d)
                side = x["side"]
                stop = x["C13"] - side * 1.25 * x["A15"]
                if early_close(dd):
                    rej["early close"] += 1
                elif self._event(dd, 780, ev):
                    rej["scheduled event"] += 1
                else:
                    why = self._admit(m, x["t13"], side, stop, x["A15"], False, None)
                    if why:
                        rej[why] += 1
                    else:
                        out.append(Signal(t=x["t13"], side=side, stop=float(stop), risk_max=0.1 * x["C13"],
                                          tag="c10_long" if side > 0 else "c10_short"))
            return out
        b = m.bars(5)
        t = b.index
        mod = (t.hour * 60 + t.minute).to_numpy()
        day = np.asarray([d.toordinal() for d in t.date])
        o, h, l, c = (b[k].to_numpy() for k in ("o", "h", "l", "c"))
        st, end = b.start.to_numpy(), b.end.to_numpy()
        a5 = ind.atr(b, 14)
        i_s = np.searchsorted(m.ns, st)
        i_e = np.searchsorted(m.ns, end)
        by_day: dict[int, list[int]] = {}
        for j in np.flatnonzero((mod + 5 >= P["first_close"]) & (mod + 5 <= P["last_close"])):
            by_day.setdefault(int(day[j]), []).append(int(j))
        for d, x in ctx.items():
            dd = date.fromordinal(d)
            if early_close(dd):
                rej["early close"] += 1
                continue
            side, O, Pc, a15 = x["side"], x["O"], x["P"], x["A15"]
            for j in by_day.get(d, []):
                if j < 123 or st[j] - st[j - 3] != 15 * NS_MIN or not np.isfinite(a5[j - 1]):
                    continue
                if (side > 0 and (c[j] < O or c[j] < Pc)) or (side < 0 and (c[j] > O or c[j] > Pc)):
                    rej["morning direction invalidated (day off)"] += 1
                    break
                lo, hi = l[j - 3:j].min(), h[j - 3:j].max()
                bb = max(P["tick"], P["b_frac"] * a5[j - 1])
                if not trigger(side, o[j], h[j], l[j], c[j], lo, hi, bb, O, Pc):
                    continue
                if self._event(dd, int(mod[j]) + 5, ev):
                    rej["scheduled event"] += 1
                    continue
                if P["mode"] == "afr_c10stop":
                    stop = c[j] - side * P["stop_cap"] * a15
                else:
                    seg = slice(i_s[j], i_e[j])
                    stop = (m.bid_l[seg].min() - bb) if side > 0 else (m.ask_h[seg].max() + bb)
                ref = lo if side > 0 else hi
                beyond = (lambda q, s=side, r=ref: s * (q - r) > 0 and s * (q - O) > 0 and s * (q - Pc) > 0)
                why = self._admit(m, int(end[j]), side, float(stop), a15, P["mode"] == "afr", beyond)
                if why:
                    rej[why] += 1
                    continue
                out.append(Signal(t=int(end[j]), side=side, stop=float(stop), risk_max=0.1 * c[j],
                                  tag="afr_long" if side > 0 else "afr_short",
                                  info={"ref": float(ref), "b": round(float(bb), 2), "a15": round(a15, 2)}))
                break
        return out

    # ── report: per eligible day, and AFR − matched C10 day by day (spec §9–10) ──
    def compare(self, m, trades, variant_trades: dict) -> list[str]:
        days = getattr(self, "diag", {}).get("eligible_days") or []
        if not days:
            return []
        tz = "America/New_York"

        def per_day(tr):
            s = pd.Series(0.0, index=pd.Index(days))
            for x in tr:
                d = pd.Timestamp(x["entry_time"]).tz_convert(tz).date().toordinal()
                if d in s.index:
                    s[d] += float(x["R"])
            return s
        base = per_day(trades)
        L = ["", f"## Per eligible day (the 13:00 context armed on {len(days)} days; 0R on days without a trade)", "",
             "| book | trades | net R per eligible day | total R |", "|---|---|---|---|"]
        L.append(f"| afr ({self.params['mode']}) | {len(trades)} | {base.mean():+.4f} | {base.sum():+.2f} |")
        for k, tr in variant_trades.items():
            v = per_day(tr)
            L.append(f"| {k} | {len(tr)} | {v.mean():+.4f} | {v.sum():+.2f} |")
        if "c10_matched" in variant_trades:
            diff = base - per_day(variant_trades["c10_matched"])
            wk = pd.Series(diff.to_numpy(), index=[date.fromordinal(d).isocalendar()[:2] for d in diff.index])
            g = wk.groupby(level=0).sum()
            rng = np.random.default_rng(7)
            boots = [rng.choice(g.to_numpy(), len(g)).sum() / len(diff) for _ in range(2000)]
            lo, hi = np.percentile(boots, [2.5, 97.5])
            L += ["", f"AFR − matched C10, per eligible day: {diff.mean():+.4f}R (95% week-block {lo:+.4f} … {hi:+.4f}); "
                      f"AFR traded {int((base != 0).sum())} of {len(days)} days, C10-matched "
                      f"{int((per_day(variant_trades['c10_matched']) != 0).sum())}."]
        rj = getattr(self, "diag", {}).get("rejections") or {}
        if rj:
            L += ["", "| rejection (this book) | count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rj.most_common()]
        return L
