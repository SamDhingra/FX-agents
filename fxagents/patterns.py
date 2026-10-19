"""Classic chart patterns from swing pivots — frozen definitions (Oct 19 2026), used first as a chart overlay and later
as candidate setups (stage 2, under the evidence rule). Display never feeds a trading decision.

Pivots: an ATR zigzag — a swing high is confirmed once price falls ZZ_K × ATR(14) below it (and vice versa), so
pivots alternate H, L, H, L. Every threshold below is in ATR at the pattern's last pivot.

  double top / bottom   two swing highs within 0.35 ATR, a trough between them ≥ 1 ATR deep, 5–80 bars apart.
                        Neckline = the trough. Target = neckline − height.
  head and shoulders    H1 L1 H2 L2 H3: head ≥ 0.5 ATR above both shoulders, shoulders within 1 ATR of each other,
  (and inverse)         neckline L1→L2 sloping ≤ 1 ATR. Target = neckline − (head − neckline).
  triangles, wedges,    two highs and two lows (the last 4 alternating pivots, ≥ 10 bars): upper line through the
  channels              highs, lower line through the lows; slopes in ATR per bar, "flat" if |slope| < 0.015:
                          ascending triangle  upper flat, lower rising        descending triangle upper falling, lower flat
                          symmetrical         upper falling, lower rising     rising wedge  both rising, lower faster
                          falling wedge       both falling, upper faster      channel up/down  both same way, parallel
                        and ≥ 80% of closes between the lines (± 0.25 ATR).
  flags                 pole: ≥ 3 ATR in ≤ 8 bars; then 5–20 bars whose range ≤ 50% of the pole and that do not
                        retrace more than 50% of it; lines through the consolidation's highs and lows.
Status: "confirmed" once a close breaks the neckline / the pattern's line in the expected direction (within 30 bars),
"failed" if price first closes beyond the other side, otherwise "forming".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ZZ_K = 1.5
FLAT = 0.015
TOL_TOP = 0.35


def atr14(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    return pd.Series(tr).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().bfill().to_numpy()


def zigzag(h: np.ndarray, l: np.ndarray, a: np.ndarray, k: float = ZZ_K) -> list[tuple[int, float, str]]:
    """Alternating swing pivots (index, price, 'H'|'L'). A swing high is confirmed when price falls k·ATR below the
    running high (and the running low is tracked from there); mirror for lows."""
    piv: list[tuple[int, float, str]] = []
    if len(h) < 3:
        return piv
    d, hi_i, lo_i = 0, 0, 0
    for i in range(1, len(h)):
        if d >= 0 and h[i] > h[hi_i]:
            hi_i = i
        if d <= 0 and l[i] < l[lo_i]:
            lo_i = i
        if d >= 0 and h[hi_i] - l[i] >= k * a[i] and i > hi_i:
            piv.append((hi_i, float(h[hi_i]), "H"))
            d, lo_i = -1, i
        elif d <= 0 and h[i] - l[lo_i] >= k * a[i] and i > lo_i:
            piv.append((lo_i, float(l[lo_i]), "L"))
            d, hi_i = 1, i
    return piv


def _status(c: np.ndarray, start: int, up_lvl, dn_lvl, want: int, horizon: int = 30):
    """First close after `start` beyond a level: want=-1 → below dn_lvl confirms, above up_lvl fails (mirror for +1).
    Levels may be callables of the bar index (sloped lines)."""
    f = lambda v, i: v(i) if callable(v) else v       # noqa: E731
    for i in range(start + 1, min(len(c), start + 1 + horizon)):
        if c[i] < f(dn_lvl, i):
            return ("confirmed" if want < 0 else "failed"), i
        if c[i] > f(up_lvl, i):
            return ("confirmed" if want > 0 else "failed"), i
    return "forming", None


def _line(i0, p0, i1, p1):
    s = (p1 - p0) / (i1 - i0) if i1 != i0 else 0.0
    return (lambda i: p0 + s * (i - i0)), s


def detect(df: pd.DataFrame) -> list[dict]:
    """Patterns in a bar frame (open/high/low/close, time index). Each: kind, dir (+1 bull, −1 bear, 0), label,
    status, i0/i1 (first/last pivot), i_break, segs [(i, price, i, price)], target (price or None)."""
    if len(df) < 20:
        return []
    h, l, c = (df[k].to_numpy(float) for k in ("high", "low", "close"))
    a = atr14(h, l, c)
    P = zigzag(h, l, a)
    out: list[dict] = []
    used_until = -1

    def add(d):
        out.append(d)

    # double top / bottom and head & shoulders (and inverse), on consecutive pivots
    for j in range(len(P)):
        if j + 2 < len(P):
            (ia, pa, ka), (ib, pb, _), (ic, pc, _) = P[j], P[j + 1], P[j + 2]
            A = a[ic]
            if 5 <= ic - ia <= 80 and abs(pa - pc) <= TOL_TOP * A:
                if ka == "H" and min(pa, pc) - pb >= 1.0 * A:
                    st, ib_ = _status(c, ic, max(pa, pc) + 0.2 * A, pb, -1)
                    add({"kind": "double_top", "dir": -1, "label": "Double top", "status": st, "i0": ia, "i1": ic,
                         "i_break": ib_, "segs": [(ia, pa, ib, pb), (ib, pb, ic, pc), (ib, pb, ib_ or len(c) - 1, pb)],
                         "target": pb - (max(pa, pc) - pb)})
                if ka == "L" and pb - max(pa, pc) >= 1.0 * A:
                    st, ib_ = _status(c, ic, pb, min(pa, pc) - 0.2 * A, +1)
                    add({"kind": "double_bottom", "dir": 1, "label": "Double bottom", "status": st, "i0": ia, "i1": ic,
                         "i_break": ib_, "segs": [(ia, pa, ib, pb), (ib, pb, ic, pc), (ib, pb, ib_ or len(c) - 1, pb)],
                         "target": pb + (pb - min(pa, pc))})
        if j + 4 < len(P):
            (i1, p1, k1), (j1, q1, _), (i2, p2, _), (j2, q2, _), (i3, p3, _) = P[j:j + 5]
            A = a[i3]
            sgn = 1 if k1 == "H" else -1                       # +1: H&S top; −1: inverse
            s1, s2, s3, n1, n2 = (sgn * x for x in (p1, p2, p3, q1, q2))
            if s2 - max(s1, s3) >= 0.5 * A and abs(s1 - s3) <= 1.0 * A and abs(n2 - n1) <= 1.0 * A and i3 - i1 <= 120:
                neck, _ = _line(j1, q1, j2, q2)
                if sgn > 0:
                    st, ib_ = _status(c, i3, p2, neck, -1)
                else:
                    st, ib_ = _status(c, i3, neck, p2, +1)
                end = ib_ or len(c) - 1
                add({"kind": "head_shoulders" if sgn > 0 else "inverse_head_shoulders", "dir": -sgn,
                     "label": "Head & shoulders" if sgn > 0 else "Inverse head & shoulders", "status": st,
                     "i0": i1, "i1": i3, "i_break": ib_,
                     "segs": [(i1, p1, j1, q1), (j1, q1, i2, p2), (i2, p2, j2, q2), (j2, q2, i3, p3),
                              (j1, q1, end, neck(end))],
                     "target": neck(i3) - sgn * (sgn * (p2 - neck(i2)))})

    # triangles, wedges, channels on the last 4 alternating pivots, non-overlapping
    for j in range(len(P) - 3):
        quad = P[j:j + 4]
        if quad[0][0] <= used_until:
            continue
        H = [p for p in quad if p[2] == "H"]
        L = [p for p in quad if p[2] == "L"]
        if len(H) != 2 or len(L) != 2:
            continue
        i0, i1 = quad[0][0], quad[-1][0]
        if i1 - i0 < 10:
            continue
        A = a[i1]
        up, su = _line(H[0][0], H[0][1], H[1][0], H[1][1])
        lo, sl = _line(L[0][0], L[0][1], L[1][0], L[1][1])
        su, sl = su / A, sl / A
        if up(i1) - lo(i1) < 0.5 * A:
            continue
        inside = np.mean([lo(i) - 0.25 * A <= c[i] <= up(i) + 0.25 * A for i in range(i0, i1 + 1)])
        if inside < 0.8:
            continue
        fu, fl = abs(su) < FLAT, abs(sl) < FLAT
        conv = su - sl < -FLAT
        par = abs(su - sl) <= 0.3 * max(abs(su), abs(sl), FLAT)
        kind = None
        if fu and sl > FLAT:
            kind, d, lab = "ascending_triangle", 1, "Ascending triangle"
        elif fl and su < -FLAT:
            kind, d, lab = "descending_triangle", -1, "Descending triangle"
        elif su < -FLAT and sl > FLAT:
            kind, d, lab = "symmetrical_triangle", 0, "Symmetrical triangle"
        elif su > FLAT and sl > FLAT and conv:
            kind, d, lab = "rising_wedge", -1, "Rising wedge"
        elif su < -FLAT and sl < -FLAT and conv:
            kind, d, lab = "falling_wedge", 1, "Falling wedge"
        elif su > FLAT and sl > FLAT and par:
            kind, d, lab = "channel_up", 1, "Channel up"
        elif su < -FLAT and sl < -FLAT and par:
            kind, d, lab = "channel_down", -1, "Channel down"
        if kind is None:
            continue
        st, ib_ = _status(c, i1, up, lo, d if d else +1)
        if d == 0 and st != "forming":                     # symmetrical: either break counts; name its direction
            d = 1 if c[ib_] > up(ib_) else -1
            st = "confirmed"
        end = ib_ or min(len(c) - 1, i1 + 10)
        add({"kind": kind, "dir": d, "label": lab, "status": st, "i0": i0, "i1": i1, "i_break": ib_,
             "segs": [(i0, up(i0), end, up(end)), (i0, lo(i0), end, lo(end))], "target": None})
        used_until = i1

    # flags: a pole then a tight counter-drift consolidation
    i = 8
    while i < len(c) - 5:
        found = False
        for sgn in (1, -1):
            s = sgn * c
            k0 = int(np.argmin(s[i - 8:i + 1])) + i - 8
            pole = s[i] - s[k0]
            if pole < 3.0 * a[i] or k0 >= i:
                continue
            for n in range(5, 21):
                e = i + n
                if e >= len(c):
                    break
                seg_h, seg_l = (h[i + 1:e + 1], l[i + 1:e + 1]) if sgn > 0 else (-l[i + 1:e + 1], -h[i + 1:e + 1])
                rng = seg_h.max() - seg_l.min()
                if rng > 0.5 * pole or s[i] - seg_l.min() > 0.5 * pole:
                    break
                if n >= 5 and (e + 1 >= len(c) or s[e + 1] > seg_h.max()):   # consolidation ends: next bar breaks out
                    xs = np.arange(i + 1, e + 1)
                    bu = np.polyfit(xs, h[i + 1:e + 1], 1)
                    bl = np.polyfit(xs, l[i + 1:e + 1], 1)
                    up_f = lambda q, b=bu: b[0] * q + b[1]                  # noqa: E731
                    lo_f = lambda q, b=bl: b[0] * q + b[1]                  # noqa: E731
                    st, ib_ = _status(c, e, up_f, lo_f, sgn, horizon=10)
                    endq = ib_ or e
                    add({"kind": "bull_flag" if sgn > 0 else "bear_flag", "dir": sgn,
                         "label": "Bull flag" if sgn > 0 else "Bear flag", "status": st, "i0": k0, "i1": e,
                         "i_break": ib_, "segs": [(k0, c[k0], i, c[i]), (i + 1, up_f(i + 1), endq, up_f(endq)),
                                                   (i + 1, lo_f(i + 1), endq, lo_f(endq))],
                         "target": None})
                    found = True
                    i = e
                    break
            if found:
                break
        i += 1
    return out


def to_json(df: pd.DataFrame, pats: list[dict], since: pd.Timestamp | None = None) -> list[dict]:
    """Bar indices → ISO times for the chart; drop patterns that end before `since`."""
    idx = df.index
    ts = lambda i: idx[int(min(max(i, 0), len(idx) - 1))].isoformat()  # noqa: E731
    out = []
    for p in pats:
        last = p["i_break"] if p["i_break"] is not None else p["i1"]
        if since is not None and idx[min(int(last), len(idx) - 1)] < since:
            continue
        out.append({"kind": p["kind"], "dir": int(p["dir"]), "label": p["label"], "status": p["status"],
                    "t0": ts(p["i0"]), "t1": ts(p["i1"]), "t_break": ts(p["i_break"]) if p["i_break"] is not None else None,
                    "segs": [[ts(a), round(float(pa), 5), ts(b), round(float(pb), 5)] for a, pa, b, pb in p["segs"]],
                    "target": round(float(p["target"]), 5) if p.get("target") is not None else None})
    return out
