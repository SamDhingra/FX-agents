"""Sam's three higher-timeframe point-of-interest models (Oct 23 2026) — shared, causal building blocks.

Rules fixed BEFORE any run (pre-registered; the three plugins only pick a model and an entry):

Common
  * Instruments NDQ, US30. Times New York. No bias filter (the models are their own context). News block ±15 min.
  * FVG on any timeframe: candles i−1, i, i+1; bullish when low[i+1] > high[i−1] (gap = high[i−1] … low[i+1]), bearish
    the mirror; gap ≥ 0.1 × ATR(14) of that timeframe; known at the close of candle i+1.
  * Entry ("entry" param, both run and judged together):
      market     at the close of the confirmation candle;
      limit_mid  limit at the midpoint of the confirmation FVG, alive for 12 confirmation candles, cancelled if the
                 target trades first.
  * Stop: beyond the extreme made since the point of interest was reached, + 0.1 × ATR(14) of the confirmation TF.
  * Target ("resting liquidity"): the nearest level on the trade's side that is still untaken at the decision —
    1H / 4H / daily / weekly swings, day and week highs & lows, Asia & London session highs & lows
    (fxagents/liquidity.level_map, each known only once confirmed) — and at least 1R from the entry price.
    AMENDMENT Oct 23 2026, after the first 12 runs and BEFORE judging them: only levels that became known within the
    last 60 days count. The first runs failed the look-ahead audit on 3 of 12 because a target could be an untaken
    level formed years earlier, which the audit's re-run on recent data cannot see, so the strategy depended on
    unbounded history. 60 days was chosen for that reason alone, not from any result; every run is redone. The
    plugins' audit warm-up is 250 days (daily ATR(14) settles well inside that).
    No such level → no trade. Out at 15:50 NY at the latest; fills only 08:30–11:30 and 13:30–15:30 NY;
    one trade at a time, at most 2 a day.

Model A — 4H FVG → 15m FVG + MSS
  POI: an unfilled 4H FVG (alive 30 4H candles; dead once a 15m candle closes beyond its far edge). Reached when a 15m
  candle trades into it. Within 8 hours of that first touch: a 15m close beyond the last confirmed 15m swing (k = 2)
  in the FVG's direction, with a 15m FVG formed by that move (known at the MSS candle or the one before).
Model B — Daily FVG or PDH/PDL taken → 1H FVG + CISD
  POI (per side, per trading day, first event only): a 1H candle trades into an unfilled daily FVG (alive 20 days),
  or trades beyond the prior trading day's low (longs) / high (shorts). Then 1H CISD: X = the extreme candle since the
  event (re-anchored on a new extreme); the series = the run of opposite-close candles ending at or before X (dojis
  skipped); CISD level = the open of its earliest candle; trigger = the first 1H close beyond that level within 12
  candles of X, with a 1H FVG whose middle candle lies between X and the trigger.
Model C — 1H SSL/BSL taken → price taps the 1H FVG → resting liquidity
  An untaken 1H swing (fractal, 3 each side) is traded through (sell-side for longs). Within 6 candles of the sweep
  a 1H FVG forms in the opposite direction (the displacement). Entry when price comes back to it:
  market = close of the first 1H candle that trades into the FVG and closes back out of its far edge's side;
  limit_mid = resting at its midpoint. Dead if price takes out the sweep extreme first or after 12 candles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import liquidity
from . import ind
from .api import Signal

HOUR = 3600 * 10 ** 9
MIN = 60 * 10 ** 9
MAX_LEVEL_AGE = 60 * 24 * HOUR          # targets: levels known within the last 60 days (amendment, see the docstring)


# ── shared pieces ─────────────────────────────────────────────────────────────────────────────────────────────────
def fvgs(b: pd.DataFrame, atr: np.ndarray, min_atr: float = 0.1) -> list[tuple]:
    """(known index = i+1, side, lo, hi) for every FVG of a candle frame (columns h l)."""
    h, l = b["h"].to_numpy(float), b["l"].to_numpy(float)
    out = []
    for i in range(1, len(h) - 1):
        a = atr[i + 1]
        if not np.isfinite(a):
            continue
        if l[i + 1] > h[i - 1] and l[i + 1] - h[i - 1] >= min_atr * a:
            out.append((i + 1, 1, h[i - 1], l[i + 1]))
        if h[i + 1] < l[i - 1] and l[i - 1] - h[i + 1] >= min_atr * a:
            out.append((i + 1, -1, h[i + 1], l[i - 1]))
    return out


def fvg_at(b: pd.DataFrame, atr: np.ndarray, k: int, side: int, min_atr: float = 0.1) -> tuple | None:
    """The FVG of `side` known at candle k (middle candle k−1), or None."""
    if k < 2:
        return None
    h, l = b["h"].to_numpy(float), b["l"].to_numpy(float)
    a = atr[k]
    if not np.isfinite(a):
        return None
    if side > 0 and l[k] > h[k - 2] and l[k] - h[k - 2] >= min_atr * a:
        return (h[k - 2], l[k])
    if side < 0 and h[k] < l[k - 2] and l[k - 2] - h[k] >= min_atr * a:
        return (h[k], l[k - 2])
    return None


class Targets:
    """Resting liquidity from fxagents/liquidity.py on this market (every weight), known/untaken at the decision."""

    def __init__(self, m) -> None:
        idx = m.idx.tz_convert("America/New_York")
        m1 = pd.DataFrame({"open": m.o, "high": m.h, "low": m.l, "close": m.c}, index=idx)
        h1 = m.bars("1h").rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})[["open", "high", "low", "close"]]
        self.lq = liquidity.Liquidity(m1, h1, min_weight=1)

    def pick(self, t: int, side: int, ref: float, risk: float, min_r: float = 1.0) -> tuple[float, str] | None:
        L = self.lq
        ok = ((L.lk <= t) & (L.lk >= t - MAX_LEVEL_AGE) & (L.taken > t) & (L.ls == side)
              & ((L.lp - ref) * side >= min_r * risk))
        ix = np.flatnonzero(ok)
        if not len(ix):
            return None
        i = ix[np.argmin(np.abs(L.lp[ix] - ref))]
        return float(L.lp[i]), liquidity.NAMES[L.lv.tf.iloc[i]]


def make_signal(P, t: int, side: int, close: float, fvg: tuple | None, stop: float, tg: Targets, tf_min: int,
                tag: str, draw: list) -> Signal | None:
    if P["entry"] == "limit_mid":
        if fvg is None:
            return None
        ref = (fvg[0] + fvg[1]) / 2
    else:
        ref = close
    risk = (ref - stop) * side
    if risk <= 0:
        return None
    tgt = tg.pick(t, side, ref, risk)
    if tgt is None:
        return None
    kw = dict(t=t, side=side, stop=float(stop), target=tgt[0], risk_max=0.1 * ref, tag=tag, draw=draw,
              info={"target_level": tgt[1], "target_r": round((tgt[0] - ref) * side / risk, 2)})
    if P["entry"] == "limit_mid":
        return Signal(entry="limit", price=float(ref), expire_min=12 * tf_min, cancel=tgt[0], **kw)
    return Signal(**kw)


def cisd_level(o: np.ndarray, c: np.ndarray, x: int, side: int, lo: int) -> float | None:
    """Long (side +1): the run of down-close candles ending at/before X (dojis skipped) → open of its earliest."""
    j = x
    want = (lambda k: c[k] < o[k]) if side > 0 else (lambda k: c[k] > o[k])
    while j >= lo and not want(j):
        j -= 1
    if j < lo:
        return None
    first = j
    k = j - 1
    while k >= lo:
        if c[k] == o[k]:
            k -= 1
            continue
        if not want(k):
            break
        first = k
        k -= 1
    return float(o[first])


# ── Model A: 4H FVG → 15m FVG + MSS ───────────────────────────────────────────────────────────────────────────────
def model_a(m, P) -> list[Signal]:
    b4, b15 = m.bars("4h"), m.bars(15)
    a4, a15 = ind.atr(b4, 14), ind.atr(b15, 14)
    e4 = b4["end"].to_numpy()
    e15, h15, l15, c15 = (b15[k].to_numpy() for k in ("end", "h", "l", "c"))
    sh, sl = ind.swings(h15, l15, 2)
    tg = Targets(m)
    out = []
    for k4, side, lo, hi in fvgs(b4, a4):
        t_known = e4[k4]
        j = int(np.searchsorted(e15, t_known, "right"))           # first 15m candle ending after the FVG is known
        touch = None
        # alive for 30 4H candles, counted as they COMPLETE (Oct 23 fix: looking up the 30th candle's end used data
        # past the decision and, on truncated data, fell back to the last candle — a look-ahead difference)
        while j < len(e15) and int(np.searchsorted(e4, e15[j], "right")) - 1 - k4 < 30:
            if (c15[j] < lo) if side > 0 else (c15[j] > hi):
                break                                                # closed beyond the far edge: FVG dead
            if touch is None and ((l15[j] <= hi) if side > 0 else (h15[j] >= lo)):
                touch = j
            if touch is not None:
                if e15[j] > e15[touch] + 8 * HOUR:
                    break
                lvl = sh[j - 1] if side > 0 else sl[j - 1]
                if np.isfinite(lvl) and side * (c15[j] - lvl) > 0:
                    g = fvg_at(b15, a15, j, side) or fvg_at(b15, a15, j - 1, side)
                    if g is not None:
                        ext = l15[touch:j + 1].min() if side > 0 else h15[touch:j + 1].max()
                        stop = ext - side * 0.1 * a15[j]
                        s = make_signal(P, int(e15[j]), side, c15[j], g, stop, tg, 15, f"A {'bull' if side > 0 else 'bear'}",
                                        [{"k": "box", "t0": int(b4.start.iloc[k4 - 1]), "t1": int(e15[j]), "hi": float(hi),
                                          "lo": float(lo), "label": "4H FVG"}])
                        if s is not None:
                            out.append(s)
                        break
            j += 1
    return out


# ── Model B: Daily FVG or PDH/PDL taken → 1H FVG + CISD ───────────────────────────────────────────────────────────
def model_b(m, P) -> list[Signal]:
    bd, b1 = m.bars("1d"), m.bars("1h")
    ad, a1 = ind.atr(bd, 14), ind.atr(b1, 14)
    ed = bd["end"].to_numpy()
    hd, ld = bd["h"].to_numpy(), bd["l"].to_numpy()
    e1, o1, h1, l1, c1 = (b1[k].to_numpy() for k in ("end", "o", "h", "l", "c"))
    tg = Targets(m)
    dfv = fvgs(bd, ad)
    out = []
    done: set = set()
    for side in (1, -1):
        alive = []                                                   # daily FVGs of this side, known and untapped
        fi = 0
        d_fv = [x for x in dfv if x[1] == side]
        event = None
        for j in range(len(e1)):
            t = e1[j]
            while fi < len(d_fv) and ed[d_fv[fi][0]] <= t - HOUR:   # known before this hour started
                kk = d_fv[fi][0]
                alive.append({"k": kk, "tapped": False, "lo": d_fv[fi][2], "hi": d_fv[fi][3]})
                fi += 1
            kd = int(np.searchsorted(ed, t - HOUR, "right")) - 1     # last daily candle complete before this hour
            # alive for 20 daily candles counted as they complete (Oct 23 fix — see model A)
            alive = [a for a in alive if not a["tapped"] and kd - a["k"] < 20]
            day = kd + 1
            if event is None and kd >= 0 and (day, side) not in done:
                hit = (l1[j] < ld[kd]) if side > 0 else (h1[j] > hd[kd])
                for a in alive:
                    if (l1[j] <= a["hi"]) if side > 0 else (h1[j] >= a["lo"]):
                        hit = True
                        a["tapped"] = True                           # tapped: no longer "unfilled"
                if hit:
                    event = {"j": j, "x": j, "day": day}
            if event is None:
                continue
            x = event["x"]
            if (l1[j] < l1[x]) if side > 0 else (h1[j] > h1[x]):
                event["x"] = x = j
            if j - x > 12 or e1[j] - e1[event["j"]] > 30 * HOUR:
                done.add((event["day"], side)); event = None
                continue
            if j == x:
                continue
            lvl = cisd_level(o1, c1, x, side, max(0, x - 24))
            if lvl is None or side * (c1[j] - lvl) <= 0:
                continue
            g = None
            for k in range(x + 1, j + 1):                         # middle candle k−1 between X and the trigger
                g = fvg_at(b1, a1, k, side) or g
            done.add((event["day"], side))
            event = None
            if g is None:
                continue
            ext = l1[x] if side > 0 else h1[x]
            stop = ext - side * 0.1 * a1[j]
            s = make_signal(P, int(t), side, c1[j], g, stop, tg, 60, f"B {'bull' if side > 0 else 'bear'}",
                            [{"k": "line", "t0": int(b1.start.iloc[x]), "t1": int(t), "px": float(lvl), "label": "CISD"}])
            if s is not None:
                out.append(s)
    out.sort(key=lambda s: s.t)
    return out


# ── Model C: 1H SSL/BSL taken → tap of the 1H FVG → resting liquidity ─────────────────────────────────────────────
def model_c(m, P) -> list[Signal]:
    b1 = m.bars("1h")
    a1 = ind.atr(b1, 14)
    e1, h1, l1, c1 = (b1[k].to_numpy() for k in ("end", "h", "l", "c"))
    n = len(e1)
    k = 3
    out = []
    tg = Targets(m)
    pivots = []                                                     # (known index, side of the liquidity, price)
    for i in range(k, n - k):
        if h1[i] > max(h1[i - k:i].max(), h1[i + 1:i + k + 1].max()):
            pivots.append((i + k, 1, h1[i]))
        if l1[i] < min(l1[i - k:i].min(), l1[i + 1:i + k + 1].min()):
            pivots.append((i + k, -1, l1[i]))
    for kn, liq_side, px in pivots:
        side = -liq_side                                           # sell-side (lows) taken → longs
        j = kn + 1
        while j < n and not ((l1[j] < px) if side > 0 else (h1[j] > px)):
            j += 1                                                 # first candle that takes the swing
        if j >= n:
            continue
        sweep = j
        ext = l1[sweep] if side > 0 else h1[sweep]
        g, gk = None, None
        for q in range(sweep + 1, min(sweep + 8, n)):
            ext = min(ext, l1[q]) if side > 0 else max(ext, h1[q])
            g = fvg_at(b1, a1, q, side)
            if g is not None and q - 1 >= sweep:
                gk = q
                break
        if g is None:
            continue
        stop = ext - side * 0.1 * a1[gk]
        draw = [{"k": "box", "t0": int(b1.start.iloc[gk - 2]), "t1": int(e1[gk]), "hi": float(g[1]), "lo": float(g[0]),
                 "label": "1H FVG"}]
        if P["entry"] == "limit_mid":
            s = make_signal(P, int(e1[gk]), side, c1[gk], g, stop, tg, 60, f"C {'bull' if side > 0 else 'bear'}", draw)
            if s is not None:
                out.append(s)
            continue
        for q in range(gk + 1, min(gk + 13, n)):
            if (l1[q] < ext) if side > 0 else (h1[q] > ext):
                break                                              # sweep extreme taken out: dead
            tapped = (l1[q] <= g[1]) if side > 0 else (h1[q] >= g[0])
            if tapped:
                if (c1[q] > g[0]) if side > 0 else (c1[q] < g[1]):
                    s = make_signal(P, int(e1[q]), side, c1[q], g, stop, tg, 60, f"C {'bull' if side > 0 else 'bear'}", draw)
                    if s is not None:
                        out.append(s)
                break
    out.sort(key=lambda s: s.t)
    return out


MODELS = {"A": model_a, "B": model_b, "C": model_c}
