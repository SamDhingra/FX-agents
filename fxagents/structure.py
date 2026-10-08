"""Market-structure primitives shared by the ICT / SMC / DTFX setups.

Every function is causal (a bar only sees what was known at its close) and O(n), so the same code
can scan a 700-bar live window or three months of 1-minute history.

Definitions used throughout (long side; shorts run the same code on a mirrored series):
  swing high/low   fractal pivot, `left`/`right` bars each side; KNOWN only `right` bars later
  BOS              close (or wick, per `rule`) beyond the last confirmed swing high while the trend is
                   already up — continuation
  CHoCH            the first such break against the prevailing trend — change of character
  MSS              a CHoCH made with displacement after a liquidity sweep (ICT's market structure shift)
  displacement     a candle whose body ≥ k × ATR and ≥ 60% of its range, closing in the move's direction
  FVG              three-candle imbalance: low[i] > high[i-2]; known at the close of bar i
  sweep            trading through a liquidity level (swing low, session low, PDL) — a raid on stops
  RVOL             a bar's (tick) volume ÷ the average volume of the same time-of-day bar over the previous
                   5 trading days — volume is strongly seasonal (Asia vs NY open), so a plain moving
                   average would call every NY-open bar "high volume". OANDA volume is tick volume (count
                   of price changes), which tracks real futures volume well enough for relative use.
  VWAP             session VWAP anchored at the 17:00 NY roll, typical price weighted by tick volume
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from .indicators import Pivot

BULL_BOS, BULL_CHOCH, BEAR_BOS, BEAR_CHOCH = 1, 2, -1, -2


# ── swings ────────────────────────────────────────────────────────────────────
def pivots_arr(h: np.ndarray, l: np.ndarray, left: int, right: int, reduce: bool = True) -> list[Pivot]:
    """Fractal swings. reduce=True: an alternating H/L sequence keeping the extreme — same rule as
    indicators.pivots, vectorised (fine for drawing, NOT causal on history). reduce=False: every raw
    fractal; feed these to swing_levels / market_structure, which apply the reduction causally."""
    n = len(h)
    w = left + right + 1
    if n < w:
        return []
    hw, lw = sliding_window_view(h, w), sliding_window_view(l, w)
    hc, lc = h[left:n - right], l[left:n - right]
    is_h = (hc == hw.max(axis=1)) & ((hw == hc[:, None]).sum(axis=1) == 1)
    is_l = (lc == lw.min(axis=1)) & ((lw == lc[:, None]).sum(axis=1) == 1)
    raw = [Pivot(int(i) + left, float(h[i + left]), "H", int(i) + left + right) for i in np.flatnonzero(is_h)]
    raw += [Pivot(int(i) + left, float(l[i + left]), "L", int(i) + left + right) for i in np.flatnonzero(is_l)]
    raw.sort(key=lambda p: (p.idx, p.kind))
    if not reduce:
        return raw
    out: list[Pivot] = []
    for p in raw:
        if out and out[-1].kind == p.kind:
            better = p.price > out[-1].price if p.kind == "H" else p.price < out[-1].price
            if better:
                out[-1] = Pivot(p.idx, p.price, p.kind, max(p.known_at, out[-1].known_at))
            continue
        out.append(p)
    return out


def pivots_pullback(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> list[Pivot]:
    """Swings confirmed by a VALIDATED PULLBACK instead of a fractal (Dave's rule as TFO's commenter puts
    it): the highest high since the last swing low becomes a swing high only once a later candle CLOSES
    below the low of the candle that made that high; a swing low likewise needs a close above the high
    of the candle that made it. Alternating H/L, causal (known_at = the validating close)."""
    n = len(h)
    out: list[Pivot] = []
    kh = kl = 0                      # candidate high / low bar since the last confirmed swing
    want = None                      # None = either; "H" or "L" = the next swing kind
    for i in range(1, n):
        if want != "L" and h[i] > h[kh]:
            kh = i
        if want != "H" and l[i] < l[kl]:
            kl = i
        if want != "L" and kh < i and c[i] < l[kh]:
            out.append(Pivot(kh, float(h[kh]), "H", i))
            want, kl = "L", kh + int(np.argmin(l[kh:i + 1]))
            continue
        if want != "H" and kl < i and c[i] > h[kl]:
            out.append(Pivot(kl, float(l[kl]), "L", i))
            want, kh = "H", kl + int(np.argmax(h[kl:i + 1]))
    return out


def swing_levels(piv: list[Pivot], n: int) -> dict[str, np.ndarray]:
    """Per bar: the current swing high / low (price and bar index) as KNOWN at that bar's close.

    Built causally from raw fractals in the order they are confirmed: a new swing of the same kind as
    the previous confirmed one (no opposite swing in between) replaces it only if it is more extreme.
    That is exactly what a live window sees; reducing the whole history first would let a later swing
    erase an earlier one before the later one was even confirmed (look-ahead)."""
    hi, hi_i = np.full(n, np.nan), np.full(n, -1, np.int64)
    lo, lo_i = np.full(n, np.nan), np.full(n, -1, np.int64)
    cur = {"H": (np.nan, -1), "L": (np.nan, -1)}
    last_kind = None
    order = sorted(piv, key=lambda q: (q.known_at, q.idx))
    ptr = 0
    for i in range(n):
        while ptr < len(order) and order[ptr].known_at <= i:
            q = order[ptr]; ptr += 1
            px, _ = cur[q.kind]
            if last_kind == q.kind and np.isfinite(px):
                better = q.price > px if q.kind == "H" else q.price < px
                if not better:
                    continue
            cur[q.kind] = (q.price, q.idx)
            last_kind = q.kind
        hi[i], hi_i[i] = cur["H"]
        lo[i], lo_i[i] = cur["L"]
    return {"hi": hi, "hi_i": hi_i, "lo": lo, "lo_i": lo_i}


def market_structure(H, L, C, piv: list[Pivot], rule: str = "close") -> dict[str, np.ndarray]:
    """trend (+1/−1/0) after each bar, the structure event on that bar (BOS/CHoCH, ± direction),
    the level that broke and where its swing sat. Each swing level can be broken once."""
    n = len(C)
    lv = swing_levels(piv, n)
    trend = np.zeros(n, np.int8)
    event = np.zeros(n, np.int8)
    brk = np.full(n, np.nan)
    brk_src = np.full(n, -1, np.int64)
    cur, used_h, used_l = 0, -1, -1
    hi, hi_i, lo, lo_i = lv["hi"], lv["hi_i"], lv["lo"], lv["lo_i"]
    up_px = C if rule == "close" else H
    dn_px = C if rule == "close" else L
    for i in range(n):
        if hi_i[i] >= 0 and hi_i[i] != used_h and up_px[i] > hi[i]:
            event[i] = BULL_BOS if cur == 1 else BULL_CHOCH
            brk[i], brk_src[i] = hi[i], hi_i[i]
            used_h, cur = hi_i[i], 1
        elif lo_i[i] >= 0 and lo_i[i] != used_l and dn_px[i] < lo[i]:
            event[i] = BEAR_BOS if cur == -1 else BEAR_CHOCH
            brk[i], brk_src[i] = lo[i], lo_i[i]
            used_l, cur = lo_i[i], -1
        trend[i] = cur
    return {"trend": trend, "event": event, "brk": brk, "brk_src": brk_src, **lv}


# ── candles ───────────────────────────────────────────────────────────────────
def displacement_up(O, H, L, C, atr, k: float = 1.0, body_frac: float = 0.6) -> np.ndarray:
    body, rng = C - O, np.maximum(H - L, 1e-12)
    return (body >= k * atr) & (body >= body_frac * rng)


def fvg_up(H, L, atr, min_atr: float = 0.1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bullish FVG confirmed at bar i: (mask, top=L[i], bottom=H[i-2])."""
    n = len(H)
    top, bot = np.full(n, np.nan), np.full(n, np.nan)
    if n >= 3:
        top[2:], bot[2:] = L[2:], H[:-2]
    ok = np.zeros(n, bool)
    ok[2:] = (top[2:] - bot[2:]) > min_atr * atr[2:]
    return ok, top, bot


# ── sessions & liquidity pools ────────────────────────────────────────────────
def session_levels(index: pd.DatetimeIndex, close_ts: pd.DatetimeIndex, O, H, L) -> dict[str, np.ndarray]:
    """ICT reference levels, each known only once its window has finished (NY time):
       asia 20:00–00:00 · london 02:00–05:00 · midnight open 00:00 · prior trading day (17:00 roll)."""
    n = len(index)
    df = pd.DataFrame({"o": O, "h": H, "l": L}, index=index)
    tday = (index + pd.Timedelta(hours=7)).normalize()          # trading day key (17:00 roll)
    hour = index.hour
    out = {k: np.full(n, np.nan) for k in ("asia_hi", "asia_lo", "lon_hi", "lon_lo", "mid_open", "pdh", "pdl")}
    g = df.groupby(tday)
    day_hi, day_lo = g["h"].max(), g["l"].min()
    pdh = day_hi.shift(1).reindex(tday).to_numpy()
    pdl = day_lo.shift(1).reindex(tday).to_numpy()
    out["pdh"], out["pdl"] = pdh, pdl
    asia = df[(hour >= 20)]
    lon = df[(hour >= 2) & (hour < 5)]
    mid = df[(hour == 0)]
    ct_h = close_ts.hour + close_ts.minute / 60.0
    in_day = np.asarray((hour < 17))                            # same trading day, after midnight
    if len(asia):
        a = asia.groupby((asia.index + pd.Timedelta(hours=7)).normalize()).agg(hi=("h", "max"), lo=("l", "min"))
        ok = in_day
        out["asia_hi"] = np.where(ok, a["hi"].reindex(tday).to_numpy(), np.nan)
        out["asia_lo"] = np.where(ok, a["lo"].reindex(tday).to_numpy(), np.nan)
    if len(lon):
        b = lon.groupby((lon.index + pd.Timedelta(hours=7)).normalize()).agg(hi=("h", "max"), lo=("l", "min"))
        ok = in_day & np.asarray(ct_h > 5.0) & np.asarray(hour >= 5)
        out["lon_hi"] = np.where(ok, b["hi"].reindex(tday).to_numpy(), np.nan)
        out["lon_lo"] = np.where(ok, b["lo"].reindex(tday).to_numpy(), np.nan)
    if len(mid):
        m = mid.groupby((mid.index + pd.Timedelta(hours=7)).normalize())["o"].first()
        out["mid_open"] = np.where(in_day, m.reindex(tday).to_numpy(), np.nan)
    return out


def window_mask(close_ts: pd.DatetimeIndex, windows: list[list[str]] | None) -> np.ndarray:
    if not windows:
        return np.ones(len(close_ts), bool)
    hm = close_ts.hour * 60 + close_ts.minute
    m = np.zeros(len(close_ts), bool)
    for a, b in windows:
        ah, am = map(int, a.split(":"))
        bh, bm = map(int, b.split(":"))
        m |= np.asarray((hm >= ah * 60 + am) & (hm < bh * 60 + bm))
    return m


# ── mirrored views: write the long side once, run it on −price for shorts ─────
@dataclass
class View:
    side: int
    O: np.ndarray
    H: np.ndarray
    L: np.ndarray
    C: np.ndarray
    piv: list[Pivot]
    ms: dict = field(default_factory=dict)
    lv: dict = field(default_factory=dict)       # session levels in this view's orientation

    def px(self, x: float) -> float:
        """Back to real price."""
        return self.side * x


def _mirror_levels(lv: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    sw = {"asia_hi": "asia_lo", "asia_lo": "asia_hi", "lon_hi": "lon_lo", "lon_lo": "lon_hi",
          "pdh": "pdl", "pdl": "pdh", "mid_open": "mid_open"}
    return {k: -lv[v] for k, v in sw.items()}


def views(df: pd.DataFrame, ctx: dict, swing: int, rule: str = "close") -> list[View]:
    key = ("_views", swing, rule)
    if key in ctx:
        return ctx[key]
    O, H, L, C = (df[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close"))
    if "_sess" not in ctx:
        ctx["_sess"] = session_levels(df.index, ctx["close_ts"], O, H, L)
    out = []
    for side in (1, -1):
        o, h, l, c = (O, H, L, C) if side > 0 else (-O, -L, -H, -C)
        piv = pivots_pullback(h, l, c) if swing == "pb" else pivots_arr(h, l, swing, swing, reduce=False)
        lv = ctx["_sess"] if side > 0 else _mirror_levels(ctx["_sess"])
        out.append(View(side, o, h, l, c, piv, market_structure(h, l, c, piv, rule), lv))
    ctx[key] = out
    return out


def htf_trend(df: pd.DataFrame, ctx: dict, rule: str = "1h", swing: int = 2) -> np.ndarray:
    """Higher-timeframe structure trend (+1/−1/0) by close, from completed HTF bars only."""
    key = ("_htf_trend", rule, swing)
    if key in ctx:
        return ctx[key]
    hb = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    if len(hb) < 2 * swing + 3:
        ctx[key] = np.zeros(len(df))
        return ctx[key]
    H, L, C = (hb[c].to_numpy(dtype=float) for c in ("high", "low", "close"))
    tr = market_structure(H, L, C, pivots_arr(H, L, swing, swing, reduce=False))["trend"].astype(float)
    known = pd.Series(tr, index=hb.index + pd.Timedelta(rule))     # usable once the HTF bar closed
    u = known.index.union(ctx["close_ts"])
    ctx[key] = known.reindex(u).ffill().reindex(ctx["close_ts"]).fillna(0).to_numpy()
    return ctx[key]


# ── volume ────────────────────────────────────────────────────────────────────
def rvol_tod(df: pd.DataFrame, days: int = 5, min_days: int = 3) -> np.ndarray:
    """Relative volume vs the same time-of-day bar on the previous `days` days (causal: today excluded)."""
    if "volume" not in df or len(df) == 0:
        return np.full(len(df), np.nan)
    v = df["volume"].astype(float).replace(0.0, np.nan)
    key = df.index.hour * 60 + df.index.minute
    base = v.groupby(key).transform(lambda x: x.shift(1).rolling(days, min_periods=min_days).mean())
    return (v / base).to_numpy()


def session_vwap(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Session VWAP and its volume-weighted standard deviation, anchored at the 17:00 NY roll."""
    n = len(df)
    if "volume" not in df or n == 0:
        return np.full(n, np.nan), np.full(n, np.nan)
    tp = ((df["high"] + df["low"] + df["close"]) / 3).to_numpy(float)
    v = np.nan_to_num(df["volume"].to_numpy(float))
    day = (df.index + pd.Timedelta(hours=7)).normalize()
    g = pd.Series(day).ne(pd.Series(day).shift()).cumsum().to_numpy()
    s_v = pd.Series(v).groupby(g).cumsum().to_numpy()
    s_pv = pd.Series(tp * v).groupby(g).cumsum().to_numpy()
    s_p2v = pd.Series(tp * tp * v).groupby(g).cumsum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        vw = np.where(s_v > 0, s_pv / s_v, np.nan)
        sd = np.sqrt(np.maximum(np.where(s_v > 0, s_p2v / s_v, np.nan) - vw * vw, 0))
    return vw, sd


VOL_MODES = ("impulse", "dry", "climax")


def vol_ok(mode: str, i: int, side: int, O: np.ndarray, C: np.ndarray, rvol: np.ndarray,
           look: int = 6, impulse: float = 1.5, dry: float = 0.9, climax: float = 2.0) -> bool:
    """Volume confirmation for a signal on bar i (one definition per mode; modes are never combined):
      impulse  the move behind the setup had participation: a bar in the trade's direction within the
               last `look` bars with RVOL ≥ 1.5
      dry      the pullback into the entry was on light volume: mean RVOL of the 3 bars before ≤ 0.9
      climax   a stop-run was absorbed: a bar AGAINST the trade within the last 4 bars with RVOL ≥ 2"""
    if mode in (None, "any"):
        return True
    if i < 4:
        return False
    if mode == "impulse":
        lo = max(0, i - look + 1)
        d = (C[lo:i + 1] - O[lo:i + 1]) * side > 0
        return bool(np.any(d & (rvol[lo:i + 1] >= impulse)))
    if mode == "dry":
        w = rvol[i - 3:i]
        return bool(np.all(np.isfinite(w)) and w.mean() <= dry)
    if mode == "climax":
        d = (C[i - 3:i + 1] - O[i - 3:i + 1]) * side < 0
        return bool(np.any(d & (rvol[i - 3:i + 1] >= climax)))
    raise ValueError(f"unknown volume mode {mode}")
