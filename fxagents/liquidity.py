"""Higher-timeframe liquidity map + two pre-registered checks (Oct 22 2026, after the US30 sweep losses).

What the TradingView scripts Sam shared do — and why this is different:
  * LuxAlgo S/R and the Nephew_Sam_ heatmap both mark fractal swing highs / lows (5–15 bars each side). The
    LuxAlgo line is drawn back at the swing although it is only confirmed `right` bars later; the heatmap asks for
    higher-timeframe pivots with lookahead_on, so on history it shows a 4H / daily level before that bar closed.
    Neither tracks whether a level has already been TAKEN, which is the part that matters for a sweep.
  * Here every level is known only from the close of the bar that confirms it, and is "untaken" until price
    trades through it. Nothing below looks past the decision time (tests check this).

Levels (each with a weight; weight ≥ 2 counts as higher timeframe):
  1H fractal (5 bars each side) 1 · Asia 20:00–00:00 / London 02:00–05:00 session high & low 1 ·
  4H fractal (3 each side) 2 · daily fractal (2 each side) 3 · prior day high / low 3 ·
  weekly fractal (2 each side) 4 · prior week high / low 4.
Daily = the 17:00 → 17:00 New York trading day, 4H on the same grid, weekly from Sunday 17:00 (bias.wall_ohlc).

The two checks — parameters fixed BEFORE any result was seen (pre-registered, never tuned):
  trap     an untaken level of weight ≥ 2 on the trade's side (highs for a long, lows for a short) was traded
           through in the 60 minutes before entry, and the entry price is back on the near side of it — the trade
           buys right after buy-side liquidity was swept (or sells after sell-side was swept).
  no_room  the nearest untaken level of weight ≥ 2 ahead of the trade is closer than 0.5 × the 1H ATR(14).

The test (python -m fxagents.liquidity test → ./fx.sh liqtest) applies each check to the playbook's own trades on
2021 → Sep 2026 (the playbook test's trades_seen_*.csv.gz, real spreads) and asks, per check:
  kept − removed average R: day-block 95% range above 0, positive in both halves, and better than removing the same
  number of trades at random (p < 0.05 over 2000 draws). Passing earns a paper filter on the scorecard — not a
  change to the practice account, and only on data already seen (the 2016–2020 vault is untouched).
`today` (./fx.sh liqtoday [days]) prints the same context for the practice account's and the playbook book's recent
trades, from OANDA candles — a check that the detector sees what the chart showed, not evidence.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .bias import wall_ohlc

WINDOW_MIN = 60          # trap: the sweep must have happened within this many minutes before entry
MIN_WEIGHT = 2           # higher timeframe = 4H and above, plus prior day / week
ROOM_ATR = 0.5           # no_room: nearest HTF level ahead closer than this × ATR(1H, 14)
NAMES = {"h1": "1H swing", "asia": "Asia", "london": "London", "h4": "4H swing", "d": "daily swing", "pd": "day high/low",
         "w": "weekly swing", "pw": "week high/low"}


# ── the level map ──────────────────────────────────────────────────────────────────────────────────────────────
def _fractals(f: pd.DataFrame, n: int, tf: str, w: int, known_end: pd.DatetimeIndex) -> list[tuple]:
    """Strict fractal highs/lows with n bars each side; known at the close of the n-th bar after the swing."""
    H, L = f["high"].to_numpy(float), f["low"].to_numpy(float)
    out = []
    for i in range(n, len(f) - n):
        known = known_end[i + n]
        hw, lw = H[i - n:i + n + 1], L[i - n:i + n + 1]
        if H[i] == hw.max() and (hw == H[i]).sum() == 1:
            out.append((H[i], 1, tf, w, known))
        if L[i] == lw.min() and (lw == L[i]).sum() == 1:
            out.append((L[i], -1, tf, w, known))
    return out


def _sessions(h1: pd.DataFrame, a: int, b: int, tf: str) -> list[tuple]:
    hrs = h1.index.hour
    s = h1[(hrs >= a) & (hrs < b)] if b > a else h1[hrs >= a]
    if not len(s):
        return []
    g = s.groupby(s.index.normalize()).agg(hi=("high", "max"), lo=("low", "min"))
    out = []
    for day, r in g.iterrows():
        known = (day + pd.Timedelta(hours=b)) if b > a else (day + pd.Timedelta(days=1))
        out += [(r.hi, 1, tf, 1, known), (r.lo, -1, tf, 1, known)]
    return out


def level_map(h1: pd.DataFrame) -> pd.DataFrame:
    """Every level with the instant it became known: columns price, side (+1 high / −1 low), tf, weight, known."""
    h1 = h1[["open", "high", "low", "close"]]
    h4 = wall_ohlc(h1, "4h", offset="1h")
    d = wall_ohlc(h1, "24h", offset="17h")
    w = wall_ohlc(h1, "168h", offset="89h")        # 1970-01-01 is a Thursday; +89h → bins start Sunday 17:00
    rows = _fractals(h1, 5, "h1", 1, h1.index + pd.Timedelta("1h"))
    rows += _fractals(h4, 3, "h4", 2, pd.DatetimeIndex(h4["end"]))
    rows += _fractals(d, 2, "d", 3, pd.DatetimeIndex(d["end"]))
    rows += _fractals(w, 2, "w", 4, pd.DatetimeIndex(w["end"]))
    for f, tf, wt in ((d, "pd", 3), (w, "pw", 4)):
        for _, r in f.iterrows():
            rows += [(r.high, 1, tf, wt, r.end), (r.low, -1, tf, wt, r.end)]
    rows += _sessions(h1, 20, 0, "asia") + _sessions(h1, 2, 5, "london")
    out = pd.DataFrame(rows, columns=["price", "side", "tf", "weight", "known"])
    out["known"] = pd.to_datetime(out["known"], utc=True).dt.tz_convert(h1.index.tz)
    return out.sort_values("known", kind="stable").reset_index(drop=True)


def _ns(ix: pd.DatetimeIndex) -> np.ndarray:
    """Epoch nanoseconds whatever the index's unit (pandas may store us)."""
    return ix.as_unit("ns").asi8


class Sparse:
    """O(1) range max / min over a fixed array (sparse table)."""

    def __init__(self, a: np.ndarray, fn) -> None:
        self.fn, self.t = fn, [a]
        k = 1
        while 2 * k <= len(a):
            p = self.t[-1]
            self.t.append(fn(p[:-k], p[k:]))
            k *= 2

    def q(self, i: int, j: int) -> float:
        """fn over a[i:j] (j exclusive); nan when empty."""
        if j <= i:
            return np.nan
        k = int(np.log2(j - i))
        return float(self.fn(self.t[k][i], self.t[k][j - (1 << k)]))


class Liquidity:
    """Answers, for a decision at time t: which levels were untaken, which were just swept, how much room is left."""

    def __init__(self, m1: pd.DataFrame, h1: pd.DataFrame) -> None:
        self.m1, self.h1 = m1, h1
        self.h1_ns = _ns(h1.index)
        self.h1_end = self.h1_ns + 3_600_000_000_000
        self.hmax, self.lmin = Sparse(h1["high"].to_numpy(float), np.maximum), Sparse(h1["low"].to_numpy(float), np.minimum)
        tr = np.maximum(h1["high"] - h1["low"], np.maximum((h1["high"] - h1["close"].shift()).abs(),
                                                          (h1["low"] - h1["close"].shift()).abs()))
        self.atr = tr.rolling(14).mean().to_numpy()
        self.m1_ns = _ns(m1.index)
        self.mH, self.mL, self.mC = (m1[k].to_numpy(float) for k in ("high", "low", "close"))
        self.set_levels(level_map(h1))

    def set_levels(self, lv: pd.DataFrame) -> None:
        self.lv = lv[lv.weight >= MIN_WEIGHT].sort_values("known", kind="stable").reset_index(drop=True)
        self.lk = _ns(pd.DatetimeIndex(self.lv["known"]))
        self.lp = self.lv["price"].to_numpy(float)
        self.ls = self.lv["side"].to_numpy(int)
        self.taken = np.array([self._taken_at(k, p, sd) for k, p, sd in zip(self.lk, self.lp, self.ls)], dtype=np.int64)

    def _taken_at(self, known: int, price: float, side: int) -> int:
        """First minute (epoch ns) at/after `known` that trades through `price`; int64 max if never."""
        never = np.iinfo(np.int64).max
        n = len(self.h1_ns)
        i = int(np.searchsorted(self.h1_ns, known, "left"))
        tab = self.hmax if side > 0 else self.lmin
        cross = (lambda v: v > price) if side > 0 else (lambda v: v < price)
        if i >= n or not cross(tab.q(i, n)):
            return never
        lo, hi = i + 1, n                                   # smallest j with a crossing inside hours [i, j)
        while lo < hi:
            mid = (lo + hi) // 2
            if cross(tab.q(i, mid)):
                hi = mid
            else:
                lo = mid + 1
        h0 = self.h1_ns[lo - 1]
        x, y = np.searchsorted(self.m1_ns, h0, "left"), np.searchsorted(self.m1_ns, h0 + 3_600_000_000_000, "left")
        ext = self.mH[x:y] if side > 0 else self.mL[x:y]
        hit = np.flatnonzero(ext > price if side > 0 else ext < price)
        return int(self.m1_ns[x + hit[0]]) if len(hit) else int(h0)

    def _extreme(self, a: pd.Timestamp, b: pd.Timestamp, side: int) -> float:
        """Highest high (side +1) / lowest low (−1) traded in [a, b): whole hours from the 1H table, edges from 1m."""
        a_ns, b_ns = pd.Timestamp(a).as_unit("ns").value, pd.Timestamp(b).as_unit("ns").value
        h_ns = self.h1_ns
        i = int(np.searchsorted(h_ns, a_ns, "left"))            # first hour starting at/after a
        j = int(np.searchsorted(h_ns + 3_600_000_000_000, b_ns, "right"))   # hours ending at/before b
        vals = []
        if j > i:
            vals.append(self.hmax.q(i, j) if side > 0 else self.lmin.q(i, j))
            e1, s2 = h_ns[i], h_ns[j - 1] + 3_600_000_000_000
        else:
            e1 = s2 = b_ns
        for lo, hi in ((a_ns, min(e1, b_ns)), (max(s2, a_ns), b_ns)):
            x, y = np.searchsorted(self.m1_ns, lo, "left"), np.searchsorted(self.m1_ns, hi, "left")
            if y > x:
                vals.append((self.mH[x:y].max()) if side > 0 else (self.mL[x:y].min()))
        vals = [v for v in vals if v == v]
        if not vals:
            return np.nan
        return max(vals) if side > 0 else min(vals)

    def at(self, t: pd.Timestamp, side: int, price: float | None = None) -> dict:
        """Context for a trade of `side` decided at `t` (entry at the last 1m close before t unless `price` given)."""
        t = pd.Timestamp(t).as_unit("ns")
        k = int(np.searchsorted(self.m1_ns, t.value, "left")) - 1
        if k < 0:
            return {"ok": False}
        p = float(price) if price is not None else float(self.mC[k])
        hi = int(np.searchsorted(self.h1_end, t.value, "right")) - 1
        atr = float(self.atr[hi]) if hi >= 0 and self.atr[hi] == self.atr[hi] else np.nan
        t0 = t - pd.Timedelta(minutes=WINDOW_MIN)
        near = np.abs(self.lp - p) <= (6 * atr if atr == atr else np.inf)
        live0 = (self.lk <= t0.value) & (self.taken >= t0.value) & near        # known and untaken an hour ago
        mine = live0 & (self.ls == side)
        swept_ix = np.flatnonzero(mine & (self.taken < t.value) & ((p < self.lp) if side > 0 else (p > self.lp)))
        swept = []
        if len(swept_ix):
            recent = self._extreme(t0, t, side)
            for i in swept_ix:
                r = self.lv.iloc[i]
                swept.append({"price": round(float(r.price), 2), "level": NAMES[r.tf], "weight": int(r.weight),
                              "depth_atr": round(abs(recent - r.price) / atr, 2) if atr == atr and recent == recent else None})
        ahead_ix = np.flatnonzero(mine & (self.taken >= t.value) & ((self.lp - p) * side > 0))
        ahead = [(abs(self.lp[i] - p), self.lv.iloc[i]) for i in ahead_ix]
        room = min(ahead, key=lambda x: x[0]) if ahead else None
        room_atr = room[0] / atr if room and atr == atr and atr > 0 else np.nan
        return {"ok": True, "price": p, "atr_1h": atr, "trap": bool(swept), "swept": swept,
                "room_atr": round(float(room_atr), 2) if room_atr == room_atr else None,
                "room_level": ({"price": round(room[1].price, 2), "level": NAMES[room[1].tf]} if room else None),
                "no_room": bool(room_atr == room_atr and room_atr < ROOM_ATR)}


# ── the test on the playbook's seen-data trades ─────────────────────────────────────────────────────────────────
def _boot_diff(kept: pd.DataFrame, rem: pd.DataFrame, B: int = 2000, seed: int = 7) -> tuple[float, float]:
    """Day-block (5 trading days) bootstrap of mean(kept) − mean(removed)."""
    rng = np.random.default_rng(seed)
    days = np.array(sorted(set(kept.day) | set(rem.day)))
    blocks = [days[i:i + 5] for i in range(0, len(days), 5)]
    kd = kept.groupby("day")["r"].agg(["sum", "count"])
    rd = rem.groupby("day")["r"].agg(["sum", "count"])
    bk = [(kd.reindex(b).fillna(0).sum()) for b in blocks]
    br = [(rd.reindex(b).fillna(0).sum()) for b in blocks]
    ks, kc = np.array([x["sum"] for x in bk]), np.array([x["count"] for x in bk])
    rs, rc = np.array([x["sum"] for x in br]), np.array([x["count"] for x in br])
    out = []
    for _ in range(B):
        ix = rng.integers(0, len(blocks), len(blocks))
        a, b = kc[ix].sum(), rc[ix].sum()
        if a and b:
            out.append(ks[ix].sum() / a - rs[ix].sum() / b)
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def judge(t: pd.DataFrame, flag: str, draws: int = 2000, seed: int = 11) -> dict:
    rem, kept = t[t[flag]], t[~t[flag]]
    res = {"check": flag, "n": len(t), "removed": len(rem), "removed_avg": round(float(rem.r.mean()), 3) if len(rem) else None,
           "kept_avg": round(float(kept.r.mean()), 3), "all_avg": round(float(t.r.mean()), 3)}
    if len(rem) < 30 or len(kept) < 30:
        return {**res, "pass": False, "why": "fewer than 30 trades on one side"}
    lo, hi = _boot_diff(kept, rem)
    mid = t.ts.sort_values().iloc[len(t) // 2]
    halves = []
    for part in (t[t.ts < mid], t[t.ts >= mid]):
        r_, k_ = part[part[flag]], part[~part[flag]]
        halves.append(round(float(k_.r.mean() - r_.r.mean()), 3) if len(r_) and len(k_) else None)
    rng = np.random.default_rng(seed)
    R = t.r.to_numpy()
    rand = np.array([np.delete(R, rng.choice(len(R), len(rem), replace=False)).mean() for _ in range(draws)])
    p = float((rand >= kept.r.mean()).mean())
    ok = lo > 0 and all(h is not None and h > 0 for h in halves) and p < 0.05
    return {**res, "diff": round(float(kept.r.mean() - rem.r.mean()), 3), "diff_ci": [round(lo, 3), round(hi, 3)],
            "halves": halves, "random_p": round(p, 4), "pass": bool(ok)}


def annotate(trades: pd.DataFrame, hist: Path) -> pd.DataFrame:
    out = []
    for sym, g in trades.groupby("sym"):
        f = hist / f"{sym}.pkl"
        if not f.exists():
            print(f"  no history for {sym} — skipped {len(g)} trades", flush=True)
            continue
        m1, h1 = pd.read_pickle(f)
        lq = Liquidity(m1, h1)
        rows = []
        for r in g.itertuples():
            c = lq.at(pd.Timestamp(r.ts), int(r.side))
            rows.append({"trap": c.get("trap", False), "no_room": c.get("no_room", False), "room_atr": c.get("room_atr"),
                         "swept": "; ".join(f"{s['level']} {s['price']}" for s in c.get("swept", []))})
        out.append(pd.concat([g.reset_index(drop=True), pd.DataFrame(rows)], axis=1))
        print(f"  {sym}: {len(g)} trades · trap {sum(x['trap'] for x in rows)} · no room {sum(x['no_room'] for x in rows)}",
              flush=True)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _fmt(j: dict) -> str:
    if "diff" not in j:
        return f"| {j['check']} | {j['removed']} of {j['n']} | {j['removed_avg']} | {j['kept_avg']} | — | — | — | **no** ({j['why']}) |"
    h = " / ".join(f"{x:+.3f}" if x is not None else "—" for x in j["halves"])
    return (f"| {j['check']} | {j['removed']} of {j['n']} | {j['removed_avg']:+.3f} | {j['kept_avg']:+.3f} | {j['diff']:+.3f} "
            f"({j['diff_ci'][0]:+.3f} to {j['diff_ci'][1]:+.3f}) | {h} | {j['random_p']:.3f} | {'**yes**' if j['pass'] else '**no**'} |")


def test(src: Path, hist: Path, out: Path) -> dict:
    files = sorted(src.glob("trades_seen_*.csv.gz"))
    if not files:
        raise SystemExit(f"no trades_seen_*.csv.gz in {src} — run ./fx.sh pbtest first")
    t = pd.concat([pd.read_csv(f).assign(cell=f.name[12:-7]) for f in files], ignore_index=True)
    t["ts"] = pd.to_datetime(t["ts"], utc=True).dt.tz_convert("America/New_York")
    t["day"] = t["day"].astype(str)
    print(f"{len(t):,} playbook trades from {len(files)} cells, {t.ts.min():%Y-%m-%d} → {t.ts.max():%Y-%m-%d}", flush=True)
    a = annotate(t, hist)
    out.mkdir(parents=True, exist_ok=True)
    a.to_csv(out / "trades_annotated.csv.gz", index=False)
    a["either"] = a["trap"] | a["no_room"]
    res = {k: judge(a, k) for k in ("trap", "no_room", "either")}
    by_cell = []
    for cell, g in a.groupby("cell"):
        row = {"cell": cell, "n": len(g)}
        for k in ("trap", "no_room"):
            row[k] = int(g[k].sum())
            row[f"{k}_avg"] = round(float(g[g[k]].r.mean()), 3) if g[k].any() else None
        row["clean_avg"] = round(float(g[~g.either].r.mean()), 3) if (~g.either).any() else None
        by_cell.append(row)
    md = ["# Higher-timeframe liquidity checks — playbook trades, 2021 → Sep 2026 (seen data)", "",
          f"Levels of weight ≥ {MIN_WEIGHT} (4H / daily / weekly swings, prior day / week high & low), each known only from "
          "the close of the bar that confirms it and untaken until price trades through it. Parameters were fixed before "
          f"this ran: **trap** = such a level on the trade's side was swept in the {WINDOW_MIN} min before entry and price "
          f"is back inside it; **no room** = the nearest untaken one ahead is closer than {ROOM_ATR} × ATR(1H, 14).", "",
          "A check passes when the trades it removes do worse than the ones it keeps: day-block 95% range of the "
          "difference above 0, positive in both halves, and better than removing the same number at random (p < 0.05). "
          "Passing earns a paper filter on the scorecard, not a change to the practice account.", "",
          "| check | removed | removed avg R | kept avg R | kept − removed (95% range) | halves | random p | pass |",
          "|---|---|---|---|---|---|---|---|"] + [_fmt(j) for j in res.values()]
    md += ["", f"All trades: {res['trap']['all_avg']:+.3f}R average. A filter that passes but leaves the kept trades "
           "below zero still leaves a losing playbook.", "", "## By cell", "",
           "| cell | trades | trap (avg R) | no room (avg R) | neither: avg R |", "|---|---|---|---|---|"]
    for r in by_cell:
        md.append(f"| {r['cell']} | {r['n']} | {r['trap']} ({r['trap_avg'] if r['trap_avg'] is not None else '—'}) | "
                  f"{r['no_room']} ({r['no_room_avg'] if r['no_room_avg'] is not None else '—'}) | {r['clean_avg']} |")
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps({"checks": res, "by_cell": by_cell,
                                                  "params": {"window_min": WINDOW_MIN, "min_weight": MIN_WEIGHT,
                                                             "room_atr": ROOM_ATR}}, indent=1, default=str))
    return res


# ── recent trades from the journals, prices from OANDA ──────────────────────────────────────────────────────────
async def _fetch(client, name: str, gran: str, start: pd.Timestamp, tz: str) -> pd.DataFrame:
    rows, cur = [], start
    for _ in range(100):
        res = await client.req("GET", f"/v3/instruments/{name}/candles",
                               params={"granularity": gran, "price": "M", "count": "5000", "includeFirst": "false",
                                       "from": cur.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.000000000Z")})
        cs = [c for c in res.get("candles", []) if c.get("complete")]
        if not cs:
            break
        rows += [{"ts": c["time"], **{k: float(c["mid"][k[0]]) for k in ("open", "high", "low", "close")}} for c in cs]
        nxt = pd.Timestamp(cs[-1]["time"])
        if nxt <= cur or len(cs) < 10:
            break
        cur = nxt
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(tz)
    return df.set_index("ts").sort_index().loc[lambda x: ~x.index.duplicated()]


async def today(cfg, days: int, out: Path) -> str:
    import sqlite3

    from .oanda import _inst, oanda_from_cfg
    from .reconcile import broker_cfg
    cfg = broker_cfg(cfg)
    tz = cfg["timezone"]
    since = pd.Timestamp.now(tz=tz) - pd.Timedelta(days=days)
    books = {"practice account": cfg["storage"]["db_path"], "playbook book": (cfg.get("shadow") or {}).get("db_path")}
    trades = []
    for book, db in books.items():
        if not db or not Path(db).exists():
            continue
        con = sqlite3.connect(db); con.row_factory = sqlite3.Row
        trades += [{**dict(r), "book": book} for r in con.execute(
            "SELECT symbol, side, strategy, opened, entry, initial_stop, r_multiple, exit_reason FROM trades "
            "WHERE opened >= ? ORDER BY opened", (since.isoformat(),))]
        con.close()
    client = oanda_from_cfg(cfg)
    lines = [f"# Liquidity context — trades since {since:%Y-%m-%d %H:%M} NY", "",
             f"trap = a 4H-or-higher level on the trade's side was swept in the {WINDOW_MIN} min before entry and price is "
             f"back inside it · room = distance to the nearest untaken 4H-or-higher level ahead, in 1H ATRs "
             f"(no room < {ROOM_ATR}). A check that the detector sees what the chart showed — not evidence.", "",
             "| book | opened (NY) | symbol | side | strategy | R | trap | swept | room (ATR 1H) | next level ahead |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    try:
        cache = {}
        for t in trades:
            sym = t["symbol"]
            if sym not in cache:
                name = _inst(cfg, sym)
                h1 = await _fetch(client, name, "H1", since - pd.Timedelta(days=120), tz)
                m1 = await _fetch(client, name, "M1", since - pd.Timedelta(days=2), tz)
                cache[sym] = Liquidity(m1, h1)
            side = 1 if t["side"] == "LONG" else -1
            opened = pd.Timestamp(t["opened"]).tz_convert(tz)
            c = cache[sym].at(opened, side, t.get("entry"))
            sw = "; ".join(f"{s['level']} {s['price']}" for s in c.get("swept", [])) or "—"
            rl = c.get("room_level")
            lines.append(f"| {t['book']} | {opened:%m-%d %H:%M} | {sym} | {t['side']} | {str(t['strategy']).split('@')[0]} | "
                         f"{t['r_multiple'] if t['r_multiple'] is not None else 'open'} | {'**yes**' if c.get('trap') else 'no'} | "
                         f"{sw} | {c.get('room_atr') if c.get('room_atr') is not None else '—'}{' **no room**' if c.get('no_room') else ''} | "
                         f"{(rl['level'] + ' ' + str(rl['price'])) if rl else '—'} |")
    finally:
        await client.aclose()
    md = "\n".join(lines) + "\n"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(md)
    return md


def main(argv=None):
    from .config import load_config
    ap = argparse.ArgumentParser(description="Higher-timeframe liquidity checks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("test")
    a1.add_argument("--src", type=Path, default=Path("data/year_test/playbook_test"))
    a1.add_argument("--hist", type=Path, default=Path("data/history_x/seen_2021_2026"))
    a1.add_argument("--out", type=Path, default=Path("data/year_test/liquidity"))
    a2 = sub.add_parser("today")
    a2.add_argument("--days", type=int, default=1)
    a2.add_argument("--out", type=Path, default=Path("data/year_test/liquidity_today"))
    a = ap.parse_args(argv)
    if a.cmd == "test":
        test(a.src, a.hist, a.out)
        print((a.out / "report.md").read_text())
    else:
        print(asyncio.run(today(load_config("config.yaml"), a.days, a.out)))


if __name__ == "__main__":
    main()
