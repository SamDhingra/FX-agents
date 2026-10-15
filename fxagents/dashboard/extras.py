"""Time machine, edge atlas and evening recap for the dashboard. Read-only: nothing here changes trading.

  timeline(main, c, day)  everything one book did on one NY day — equity, trades with their events, every setup seen
                          (and why it was taken or passed), Jev decisions, news, 5-minute candles — for the slider
  atlas(main)             the setup map as terrain: instrument × setup × hour, height = expectancy shrunk toward the
                          setup's own record, fog = how little data stands behind it, plus how many "peaks" pure luck
                          would produce among that many cells
  recap(main, day)        the day in numbers per book, and a short plain-language script (spoken in the browser)
"""
from __future__ import annotations

import json
import math
from collections import defaultdict

import numpy as np
import pandas as pd

SHRINK_K = 12


def _day_bounds(main, day: str | None) -> tuple[str, pd.Timestamp, pd.Timestamp]:
    tz = main.cfg["timezone"]
    now = pd.Timestamp(main.state.now) if main.state.now is not None else pd.Timestamp.now(tz=tz)
    if now.tzinfo is None:
        now = now.tz_localize(tz)
    d = pd.Timestamp(day).tz_localize(tz) if day else now.normalize()
    return d.strftime("%Y-%m-%d"), d, d + pd.Timedelta(days=1)


# ── Time machine ─────────────────────────────────────────────────────────────────────────────────────────────────
def timeline(main, c, day: str | None) -> dict:
    ds, a, b = _day_bounds(main, day)
    sa, sb = a.isoformat(), b.isoformat()
    db = c.journal.db
    eq = [[r[0], r[1]] for r in db.execute("SELECT ts, equity FROM equity WHERE ts >= ? AND ts < ? ORDER BY ts", (sa, sb))]
    if len(eq) > 1500:
        eq = eq[:: math.ceil(len(eq) / 1500)]
    tr = []
    for r in db.execute("SELECT * FROM trades WHERE opened < ? AND (closed IS NULL OR closed >= ?) ORDER BY opened", (sb, sa)):
        t = dict(r)
        t["events"] = json.loads(t.get("events") or "[]")
        tr.append({k: t.get(k) for k in ("id", "symbol", "side", "strategy", "opened", "closed", "entry", "initial_stop",
                                          "final_stop", "exit_price", "r_multiple", "realized", "exit_reason", "jev_quality",
                                          "events", "notes")})
    sig = [dict(r) for r in db.execute("SELECT ts, symbol, strategy, side, action, why FROM signals WHERE ts >= ? AND ts < ? "
                                       "ORDER BY ts LIMIT 1500", (sa, sb))]
    dec = []
    for r in main.journal.db.execute("SELECT ts, kind, source, symbol, strategy, outputs FROM decisions WHERE ts >= ? AND ts < ? "
                                     "ORDER BY ts LIMIT 600", (sa, sb)):
        d = dict(r)
        d["outputs"] = json.loads(d["outputs"] or "null")
        dec.append(d)
    bars = {}
    for sym in main.cfg["instruments"]:
        try:
            m1 = main.store.m1(sym)
            seg = m1[(m1.index >= a) & (m1.index < b)]
            if len(seg):
                f = seg.resample("5min", label="left", closed="left").agg(
                    {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
                bars[sym] = [[ts.isoformat(), round(float(x.open), 5), round(float(x.high), 5), round(float(x.low), 5),
                              round(float(x.close), 5)] for ts, x in f.iterrows()]
        except Exception:  # noqa: BLE001
            pass
    news = [{"ts": e["ts"].isoformat(), "title": e["title"], "tier": e["tier"]} for e in (getattr(main.news, "events", None) or [])
            if a <= e["ts"] < b] if main.news else []
    return {"day": ds, "start": sa, "end": sb, "equity": eq, "trades": tr, "signals": sig, "decisions": dec,
            "bars": bars, "news": news}


# ── Edge atlas ───────────────────────────────────────────────────────────────────────────────────────────────────
def atlas(main) -> dict:
    h = getattr(main, "setup_map", None)
    rows = getattr(getattr(h, "map", None), "rows", None)
    if not rows:
        return {"state": (getattr(h, "status", None) or {}).get("state", "off") if h else "off", "cells": []}
    from ..setup_map import setup_name
    acc: dict[tuple, list] = defaultdict(list)
    fam: dict[tuple, list] = defaultdict(list)
    for sym, sid, tfl, hour, wd, r in rows:
        n = setup_name(sid)
        acc[(sym, n, int(hour))].append(float(r))
        fam[(sym, n)].append(float(r))
    cells, ntest, sig = [], 0, 0
    for (sym, n, hr), rs in acc.items():
        x = np.asarray(rs)
        k = len(x)
        fo = float(np.mean(fam[(sym, n)]))
        mu = float(x.mean())
        sd = float(x.std(ddof=1)) if k > 1 else 1.0
        t = mu / (sd / math.sqrt(k)) if k > 1 and sd > 0 else 0.0
        shrunk = (mu * k + fo * SHRINK_K) / (k + SHRINK_K)
        if k >= 10:
            ntest += 1
            sig += abs(t) >= 2
        cells.append({"symbol": sym, "setup": n, "hour": hr, "n": k, "avg_r": round(mu, 3), "shrunk": round(shrunk, 3),
                      "win": round(float((x > 0).mean()), 3), "t": round(t, 2), "fog": round(max(0.0, 1 - k / 80), 3)})
    return {"state": "ready", "cells": cells, "tested": ntest, "peaks": sig, "luck_peaks": round(ntest * 0.0455, 1),
            "symbols": list(main.cfg["instruments"]), "built": (h.status or {}).get("built") if h else None}


# ── Evening recap ────────────────────────────────────────────────────────────────────────────────────────────────
def recap(main, day: str | None) -> dict:
    from . import ghosts
    ds, a, b = _day_bounds(main, day)
    sa, sb = a.isoformat(), b.isoformat()
    books = [("live", main)] + list((getattr(main, "shadows", None) or {}).items())
    out, lines = [], []
    for key, c in books:
        db = c.journal.db
        tr = [dict(r) for r in db.execute("SELECT symbol, side, strategy, r_multiple, realized, exit_reason FROM trades "
                                          "WHERE status='closed' AND closed >= ? AND closed < ? ORDER BY closed", (sa, sb))]
        sig = db.execute("SELECT action, COUNT(*) FROM signals WHERE ts >= ? AND ts < ? GROUP BY action", (sa, sb)).fetchall()
        seen = {r[0]: r[1] for r in sig}
        reasons = [r[0] for r in db.execute("SELECT why FROM signals WHERE ts >= ? AND ts < ? AND action != 'taken'", (sa, sb))]
        rc: dict[str, int] = {}
        for w in reasons:
            f = ghosts.filter_of("passed", w)
            rc[f] = rc.get(f, 0) + 1
        try:
            ghosts.ensure(c.journal)
            gsum = {r[0]: (r[1], r[2]) for r in db.execute(
                "SELECT filter, COUNT(*), SUM(r) FROM ghosts WHERE ts >= ? AND ts < ? AND r IS NOT NULL AND action != 'taken' "
                "GROUP BY filter", (sa, sb))}
        except Exception:  # noqa: BLE001
            gsum = {}
        rs = [t["r_multiple"] or 0 for t in tr]
        best = max(tr, key=lambda t: t["r_multiple"] or -9) if tr else None
        worst = min(tr, key=lambda t: t["r_multiple"] or 9) if tr else None
        bk = {"book": key, "mode": getattr(c, "selection_mode", key), "trades": len(tr), "sum_r": round(sum(rs), 2),
              "pnl": round(sum(t["realized"] or 0 for t in tr), 2), "wins": sum(1 for x in rs if x > 0),
              "best": best, "worst": worst, "seen": sum(seen.values()), "taken": seen.get("taken", 0),
              "passed_by": sorted(rc.items(), key=lambda x: -x[1])[:4],
              "ghosts": {k: {"n": v[0], "saved_r": round(-(v[1] or 0), 2)} for k, v in gsum.items()},
              "open": sum(1 for p in c.state.positions.values() if p.status == "open")}
        out.append(bk)
    # the script: a short paragraph per book, live first, then the paper books that traded
    nm = lambda k: "your practice account" if k == "live" else "the " + k.replace("_", " ") + " book"
    L = out[0]
    if L["trades"]:
        s = f"Today {nm('live')} closed {L['trades']} trade{'s' if L['trades'] != 1 else ''}, {L['wins']} winning, " \
            f"for {L['sum_r']:+.2f}R and {'a gain' if L['pnl'] >= 0 else 'a loss'} of ${abs(L['pnl']):,.0f}."
        if L["best"] and L["trades"] > 1:
            s += f" The best was {L['best']['symbol']} at {L['best']['r_multiple']:+.2f}R"
            s += f"; the worst {L['worst']['symbol']} at {L['worst']['r_multiple']:+.2f}R." if L["worst"] else "."
    else:
        s = f"No trades closed today in {nm('live')}."
    lines.append(s)
    if L["seen"]:
        p = L["seen"] - L["taken"]
        s = f"It saw {L['seen']} setups and took {L['taken']}."
        if L["passed_by"]:
            s += " It passed on " + str(p) + ", mostly because of " + ", ".join(f"{k.lower()} ({n})" for k, n in L["passed_by"][:2]) + "."
        lines.append(s)
    g = sorted(L["ghosts"].items(), key=lambda x: -abs(x[1]["saved_r"]))
    if g:
        k, v = g[0]
        lines.append(f"The {k.lower()} {'saved' if v['saved_r'] >= 0 else 'cost'} about {abs(v['saved_r']):.1f}R on "
                     f"{v['n']} blocked setup{'s' if v['n'] != 1 else ''}, by the ghost yardstick.")
    traded = [x for x in out[1:] if x["trades"]]
    if traded:
        lines.append("On paper: " + "; ".join(f"{x['book'].replace('_', ' ')} {x['trades']} trade{'s' if x['trades'] != 1 else ''}, "
                                              f"{x['sum_r']:+.2f}R" for x in traded) + ".")
    opn = sum(x["open"] for x in out)
    if opn:
        lines.append(f"{opn} position{'s are' if opn != 1 else ' is'} still open across the books.")
    if not main.state.trading_enabled:
        lines.append(f"Entries are paused: {main.state.halt_reason}.")
    return {"day": ds, "books": out, "script": " ".join(lines), "lines": lines}
