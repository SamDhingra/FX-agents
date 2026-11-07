"""Analysis page (Nov 4 2026, Sam: "to do the analysis we have to go through lot of hoops"). One request answers what
used to take a diagnostic run: per setup × instrument scorecard, why signals were not taken (by reason), results by
hour, weekday, session, instrument and direction, exits, bias relation, the trades that gave back +1R, the R curve and
distribution, holding time and how much of each trade's best move was kept. Read-only, per book, over a range of days,
narrowed by filters (instrument, setup, direction, timeframe, exit profile, session, bias).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

NY = "America/New_York"

# signal refusal text → a reason anyone can read at a glance (order matters: first match wins)
REASONS = [
    ("Bias rule", r"bias|counter to"),
    ("Outside entry window", r"entry window|session|flat time|last 20 min"),
    ("News blackout", r"news"),
    ("Position limits", r"already has|max open|index group|opposite position|cell already|one index position"),
    ("Spread too large", r"cost .*R of the stop|spread"),
    ("Jev said no", r"\bjev\b"),
    ("Book halted / paused", r"halted|paused|kill|drawdown|daily loss"),
    ("Instrument off", r" is off|watch-only|trade: false"),
    ("Chop / trend routing", r"chop|regime|trend route"),
    ("Stop / size", r"stop|size|qty|units|risk"),
]
SESSIONS = (("Asia", 18, 3), ("London", 3, 8), ("New York", 8, 18))   # NY clock: [start, end) hours; Asia wraps midnight
FILTERS = ("symbol", "setup", "side", "tf", "profile", "session", "bias")


def reason_of(why: str | None) -> str:
    w = (why or "").lower()
    for name, pat in REASONS:
        if re.search(pat, w):
            return name
    return "Other"


def setup_of(strategy: str | None) -> str:
    """'sr_rejection:30m@pb-us30-d-trend' → 'sr_rejection'; 'c10_afternoon:5m@v2' → 'c10_afternoon'."""
    return str(strategy or "?").split(":")[0].split("@")[0]


def tf_of(strategy: str | None) -> str:
    m = re.search(r":(\d+[mhd])@", str(strategy or ""))
    return m.group(1) if m else "—"


def profile_of(strategy: str | None) -> str:
    """The playbook cell's exit profile from its id: …-trend / …-scalp / …-tp2 → trend / scalp / tp2; else standard."""
    s = str(strategy or "")
    m = re.search(r"-(trend|scalp|tp[\d.]+)$", s)
    return m.group(1) if m else "standard"


def session_of(hour: int) -> str:
    for name, a, b in SESSIONS:
        if (a <= hour < b) if a < b else (hour >= a or hour < b):
            return name
    return "Other"


def side_of(x) -> str:
    s = str(x).upper()
    return "LONG" if s in ("LONG", "1", "BUY", "1.0") else "SHORT" if s in ("SHORT", "-1", "SELL", "-1.0") else s


def _ny(s: pd.Series) -> pd.Series:
    t = pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    return t.dt.tz_convert(NY)


def _stats(g) -> dict:
    """R and pip statistics of a group of trades (a frame with r_multiple and pips, or a bare R series)."""
    if isinstance(g, pd.Series):
        g = pd.DataFrame({"r_multiple": g})
    g = g[g["r_multiple"].notna()]
    n = len(g)
    if not n:
        return {"n": 0, "win": None, "avg": None, "sum": 0.0, "pips": None, "win_pips": None, "loss_pips": None,
                "avg_pips": None, "payoff": None, "payoff_r": None, "win_nz": None, "flat_n": 0}
    r = g["r_multiple"]
    out = {"n": int(n), "win": round(float((r > 0).mean()), 3), "avg": round(float(r.mean()), 3), "sum": round(float(r.sum()), 2)}
    # payoff in R (Nov 7 2026, Astra review): average winning R ÷ |average losing R|. Exactly-0R trades are neither, so
    # the break-even win rate 1/(1+payoff) is compared with wins ÷ (wins + losses), the same cohort.
    rw, rl = r[r > 0], r[r < 0]
    out["payoff_r"] = round(float(rw.mean() / abs(rl.mean())), 2) if len(rw) and len(rl) else None
    out["win_nz"] = round(float(len(rw) / (len(rw) + len(rl))), 3) if len(rw) + len(rl) else None
    out["flat_n"] = int((r == 0).sum())
    p = g["pips"].dropna() if "pips" in g else pd.Series(dtype=float)
    if len(p):
        w, lo = p[p > 0], p[p <= 0]
        wp = float(w.mean()) if len(w) else None
        lp = float(lo.mean()) if len(lo) else None
        out.update(pips=round(float(p.sum()), 1), avg_pips=round(float(p.mean()), 1), win_pips=round(wp, 1) if wp is not None else None,
                   loss_pips=round(lp, 1) if lp is not None else None,
                   payoff=round(wp / abs(lp), 2) if wp is not None and lp not in (None, 0) else None)
    else:
        out.update(pips=None, avg_pips=None, win_pips=None, loss_pips=None, payoff=None)
    return out


def _group(t: pd.DataFrame, key, label: str, order=None) -> list[dict]:
    rows = [{label: (k if not isinstance(k, (np.integer,)) else int(k)), **_stats(g)} for k, g in t.groupby(key)]
    if order:
        rows.sort(key=lambda r: order.index(r[label]) if r[label] in order else 99)
    return rows


def _tag(t: pd.DataFrame, ts_col: str, strat_col: str) -> pd.DataFrame:
    t["setup"] = t[strat_col].map(setup_of)
    t["tf"] = t[strat_col].map(tf_of)
    t["profile"] = t[strat_col].map(profile_of)
    t["session"] = t[ts_col].dt.hour.map(session_of) if len(t) else pd.Series(dtype=str)
    t["side"] = t["side"].map(side_of)
    return t


def add_pips(t: pd.DataFrame, cfg: dict | None) -> pd.DataFrame:
    """Pips per trade, as the Trades page shows them (units.trade): net P&L ÷ ($ per pip × all units traded), so partial
    exits and adds are included. Gold 1 pip = $0.10, indices 1 pip = 1 point, forex 0.0001 (per-instrument pip_size)."""
    if cfg is None or not len(t):
        t["pips"] = np.nan
        return t
    from .. import units
    pip = t["symbol"].map(lambda s: units.pip_size(cfg, s))
    mult = t["symbol"].map(lambda s: float((cfg["instruments"].get(s) or {}).get("multiplier", 1)))
    qg = t["qty_gross"].fillna(t["qty_initial"]).astype(float)
    t["pips"] = np.where((qg > 0) & t["realized"].notna(), t["realized"].astype(float) / (mult * pip * qg.where(qg > 0, np.nan)), np.nan)
    return t


def build(db, days: int = 30, now: pd.Timestamp | None = None, filters: dict | None = None, cfg: dict | None = None) -> dict:
    now = now if now is not None else pd.Timestamp.now(tz=NY)
    since = now - pd.Timedelta(days=days)
    f = {k: v for k, v in (filters or {}).items() if k in FILTERS and v not in (None, "", "all")}
    t = pd.read_sql_query("SELECT id, symbol, side, strategy, opened, closed, r_multiple, mfe_r, mae_r, exit_reason, bias_mode, "
                          "realized, qty_initial, qty_gross FROM trades WHERE status='closed' AND r_multiple IS NOT NULL", db)
    t["opened_ny"] = _ny(t["opened"])
    t["closed_ny"] = _ny(t["closed"])
    t = _tag(t[t["opened_ny"] >= since].copy(), "opened_ny", "strategy")
    t["bias"] = t["bias_mode"].fillna("—").astype(str)
    t = add_pips(t, cfg)
    sig = pd.read_sql_query("SELECT ts, symbol, strategy, side, action, why FROM signals", db)
    sig["ts_ny"] = _ny(sig["ts"])
    sig = _tag(sig[sig["ts_ny"] >= since].copy(), "ts_ny", "strategy")
    sig["reason"] = [("Taken" if a == "taken" else reason_of(w)) for a, w in zip(sig["action"], sig["why"])]

    # what can be filtered on (from the whole range, before filtering, so a choice never hides the others)
    opts = {k: sorted({str(x) for x in pd.concat([t[k], sig[k]]) if str(x) not in ("nan", "")}) for k in ("symbol", "setup", "side", "tf", "profile")}
    opts["session"] = [s[0] for s in SESSIONS]
    opts["bias"] = sorted({str(x) for x in t["bias"]})
    for k, v in f.items():
        t = t[t[k].astype(str) == str(v)]
        if k in sig.columns:                      # signals have no bias mode: that filter applies to trades only
            sig = sig[sig[k].astype(str) == str(v)]

    # filters that could not apply to signals (signals carry no bias mode): the page says so beside the signal counts
    sig_unscoped = [k for k in f if k not in sig.columns]
    out: dict = {"days": days, "since": since.isoformat(), "filters": f, "options": opts, "totals": _stats(t),
                 "signal_scope": {"unapplied": sig_unscoped}, "date_basis": "entered",
                 "pnl": round(float(t["realized"].fillna(0).sum()), 2)}
    # 1. scorecard: setup × instrument (with what happened to its signals)
    rows = []
    fun = sig.groupby(["setup", "symbol"])["reason"].value_counts().unstack(fill_value=0) if len(sig) else pd.DataFrame()
    keys = set(map(tuple, t[["setup", "symbol"]].drop_duplicates().to_numpy())) | set(fun.index.tolist())
    for setup, sym in sorted(keys):
        g = t[(t.setup == setup) & (t.symbol == sym)]
        st = _stats(g)
        give = int(((g["mfe_r"] >= 1) & (g["r_multiple"] <= 0)).sum())
        fr = fun.loc[(setup, sym)].to_dict() if (setup, sym) in fun.index else {}
        refused = {k: int(v) for k, v in sorted(fr.items(), key=lambda kv: -kv[1]) if k != "Taken" and v}
        last = g["opened_ny"].max() if len(g) else None
        rows.append({"setup": setup, "symbol": sym, **st, "givebacks": give,
                     "avg_mfe": round(float(g["mfe_r"].mean()), 2) if len(g) and g["mfe_r"].notna().any() else None,
                     "signals": int(sum(fr.values())), "taken": int(fr.get("Taken", 0)), "refused": refused,
                     "last": last.isoformat() if last is not None and pd.notna(last) else None})
    out["scorecard"] = sorted(rows, key=lambda r: (-(r["sum"] or 0), r["setup"]))
    # 2. why signals were not taken
    out["refusals"] = [{"reason": k, "n": int(v)} for k, v in sig[sig.reason != "Taken"]["reason"].value_counts().items()]
    out["signals"] = {"seen": int(len(sig)), "taken": int((sig.reason == "Taken").sum())}
    # 3. when: hour, weekday, session (New York entry time)
    out["by_hour"] = [{"hour": int(h), **_stats(g)} for h, g in t.groupby(t["opened_ny"].dt.hour)]
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    out["by_weekday"] = [{"day": names[int(d)], **_stats(g)} for d, g in t.groupby(t["opened_ny"].dt.dayofweek)]
    out["by_session"] = _group(t, "session", "session", [s[0] for s in SESSIONS])
    # 4. what: instrument, direction, timeframe, exit profile
    out["by_symbol"] = sorted(_group(t, "symbol", "symbol"), key=lambda r: -r["sum"])
    out["by_side"] = _group(t, "side", "side", ["LONG", "SHORT"])
    out["by_tf"] = sorted(_group(t, "tf", "tf"), key=lambda r: pd.Timedelta(r["tf"]) if r["tf"] != "—" else pd.Timedelta(0))
    out["by_profile"] = _group(t, "profile", "profile", ["standard", "scalp", "trend"])
    # 5. exits and bias relation
    out["exits"] = sorted([{"reason": str(k or "?"), **_stats(g)} for k, g in t.groupby(t["exit_reason"].fillna("?"))],
                          key=lambda r: -r["n"])
    out["bias"] = sorted([{"mode": k, **_stats(g)} for k, g in t.groupby("bias")], key=lambda r: -r["n"])
    # 6. trades that reached +1R and still closed at or below zero
    gb = t[(t["mfe_r"] >= 1) & (t["r_multiple"] <= 0)].sort_values("opened_ny", ascending=False)
    out["givebacks"] = [{"id": r.id, "opened": r.opened_ny.isoformat(), "symbol": r.symbol, "side": r.side, "setup": r.setup,
                         "mfe": round(float(r.mfe_r), 2), "r": round(float(r.r_multiple), 2), "exit": r.exit_reason,
                         "pips": round(float(r.pips), 1) if pd.notna(r.pips) else None}
                        for r in gb.head(25).itertuples()]
    nm = int(t["mfe_r"].notna().sum())
    out["giveback_share"] = round(float(len(gb) / nm), 3) if nm else None    # of trades with a recorded best move
    # 7. the R curve, streaks and drawdown (closed order)
    tc = t.sort_values("closed_ny")
    c = tc["r_multiple"].to_numpy(float)
    if len(c):
        cum = c.cumsum()
        peak = np.maximum.accumulate(np.maximum(cum, 0))
        best = worst = cur = 0
        for x in c:
            cur = (cur + 1 if cur >= 0 else 1) if x > 0 else (cur - 1 if cur <= 0 else -1)
            best, worst = max(best, cur), min(worst, cur)
        out["streaks"] = {"max_dd_r": round(float((cum - peak).min()), 2), "longest_win": best, "longest_loss": -worst, "current": int(cur)}
        # trade sequence (evenly spaced by trade, not by time), starting at 0. Thinned to ≤ 300 points, but every
        # thinned bucket keeps its own high and low, and the extremes come from the full series (Astra review).
        step = max(1, -(-len(c) // 300))
        pts = [{"t": tc["closed_ny"].iloc[0].isoformat(), "r": 0.0, "i": 0}]
        for a0 in range(0, len(c), step):
            seg = range(a0, min(a0 + step, len(c)))
            keep = sorted({seg[0], seg[-1], max(seg, key=lambda i: cum[i]), min(seg, key=lambda i: cum[i])})
            pts += [{"t": tc["closed_ny"].iloc[i].isoformat(), "r": round(float(cum[i]), 2), "i": i + 1} for i in keep]
        out["curve"] = pts
        out["curve_stats"] = {"n": int(len(c)), "high": round(float(max(0.0, cum.max())), 2),
                              "low": round(float(min(0.0, cum.min())), 2), "last": round(float(cum[-1]), 2)}
    else:
        out["streaks"], out["curve"], out["curve_stats"] = None, [], None
    # 8. distribution of results, and how much of the best move was kept
    edges = [-np.inf, -1.0, -0.5, -0.0001, 0.5, 1.0, 2.0, np.inf]
    labels = ["≤ −1R", "−1 to −0.5R", "−0.5 to 0", "0 to +0.5R", "+0.5 to +1R", "+1 to +2R", "> +2R"]
    hist = pd.cut(t["r_multiple"], edges, labels=labels).value_counts().reindex(labels, fill_value=0) if len(t) else pd.Series(0, index=labels)
    out["distribution"] = [{"bucket": k, "n": int(v)} for k, v in hist.items()]
    w, lo = t[t.r_multiple > 0], t[t.r_multiple <= 0]
    mf = lambda x: round(float(x.mean()), 2) if len(x) and x.notna().any() else None  # noqa: E731
    # same cohort on both sides (Astra review): winners whose best move was recorded and positive
    we = w[w["mfe_r"].notna() & (w["mfe_r"] > 0)]
    tm = t[t["mfe_r"].notna()]                                   # trades with a recorded best move
    reached = tm[tm["mfe_r"] >= 1]
    out["excursion"] = {"win_mfe": mf(we["mfe_r"]), "win_r": mf(we["r_multiple"]), "loss_mfe": mf(lo["mfe_r"]), "loss_r": mf(lo["r_multiple"]),
                        "loss_mae": mf(lo["mae_r"]), "win_mae": mf(w["mae_r"]),
                        "kept": round(float(we["r_multiple"].sum() / we["mfe_r"].sum()), 2) if len(we) else None,
                        "kept_cov": [int(len(we)), int(len(w))],
                        "reached_1r": round(float(len(reached) / len(tm)), 3) if len(tm) else None,
                        "mfe_cov": [int(len(tm)), int(len(t))],
                        "gave_back_of_reached": round(float((reached["r_multiple"] <= 0).mean()), 3) if len(reached) else None,
                        "reached_n": int(len(reached))}
    # 9. holding time
    mins = (t["closed_ny"] - t["opened_ny"]).dt.total_seconds() / 60
    hb = pd.cut(mins, [0, 15, 60, 240, np.inf], labels=["< 15 min", "15–60 min", "1–4 h", "> 4 h"], right=False)
    out["by_hold"] = [{"hold": str(k), **_stats(g)} for k, g in t.groupby(hb, observed=True)]
    # 10. low win rate, positive pips: setups whose winners are big enough to carry many small losses
    out["big_payoff"] = sorted([r for r in rows if r["n"] >= 5 and (r["win"] or 0) < 0.45 and (r.get("pips") or 0) > 0],
                               key=lambda r: -(r.get("pips") or 0))
    out["pips_by_symbol"] = {sym: _stats(g)["pips"] for sym, g in t.groupby("symbol")}
    return out
