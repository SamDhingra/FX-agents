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


def _stats(r: pd.Series) -> dict:
    r = r.dropna()
    n = len(r)
    if not n:
        return {"n": 0, "win": None, "avg": None, "sum": 0.0}
    return {"n": int(n), "win": round(float((r > 0).mean()), 3), "avg": round(float(r.mean()), 3), "sum": round(float(r.sum()), 2)}


def _group(t: pd.DataFrame, key, label: str, order=None) -> list[dict]:
    rows = [{label: (k if not isinstance(k, (np.integer,)) else int(k)), **_stats(g["r_multiple"])} for k, g in t.groupby(key)]
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


def build(db, days: int = 30, now: pd.Timestamp | None = None, filters: dict | None = None) -> dict:
    now = now if now is not None else pd.Timestamp.now(tz=NY)
    since = now - pd.Timedelta(days=days)
    f = {k: v for k, v in (filters or {}).items() if k in FILTERS and v not in (None, "", "all")}
    t = pd.read_sql_query("SELECT id, symbol, side, strategy, opened, closed, r_multiple, mfe_r, mae_r, exit_reason, bias_mode, "
                          "realized FROM trades WHERE status='closed' AND r_multiple IS NOT NULL", db)
    t["opened_ny"] = _ny(t["opened"])
    t["closed_ny"] = _ny(t["closed"])
    t = _tag(t[t["opened_ny"] >= since].copy(), "opened_ny", "strategy")
    t["bias"] = t["bias_mode"].fillna("—").astype(str)
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

    out: dict = {"days": days, "since": since.isoformat(), "filters": f, "options": opts, "totals": _stats(t["r_multiple"]),
                 "pnl": round(float(t["realized"].fillna(0).sum()), 2)}
    # 1. scorecard: setup × instrument (with what happened to its signals)
    rows = []
    fun = sig.groupby(["setup", "symbol"])["reason"].value_counts().unstack(fill_value=0) if len(sig) else pd.DataFrame()
    keys = set(map(tuple, t[["setup", "symbol"]].drop_duplicates().to_numpy())) | set(fun.index.tolist())
    for setup, sym in sorted(keys):
        g = t[(t.setup == setup) & (t.symbol == sym)]
        st = _stats(g["r_multiple"])
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
    out["by_hour"] = [{"hour": int(h), **_stats(g["r_multiple"])} for h, g in t.groupby(t["opened_ny"].dt.hour)]
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    out["by_weekday"] = [{"day": names[int(d)], **_stats(g["r_multiple"])} for d, g in t.groupby(t["opened_ny"].dt.dayofweek)]
    out["by_session"] = _group(t, "session", "session", [s[0] for s in SESSIONS])
    # 4. what: instrument, direction, timeframe, exit profile
    out["by_symbol"] = sorted(_group(t, "symbol", "symbol"), key=lambda r: -r["sum"])
    out["by_side"] = _group(t, "side", "side", ["LONG", "SHORT"])
    out["by_tf"] = sorted(_group(t, "tf", "tf"), key=lambda r: pd.Timedelta(r["tf"]) if r["tf"] != "—" else pd.Timedelta(0))
    out["by_profile"] = _group(t, "profile", "profile", ["standard", "scalp", "trend"])
    # 5. exits and bias relation
    out["exits"] = sorted([{"reason": str(k or "?"), **_stats(g["r_multiple"])} for k, g in t.groupby(t["exit_reason"].fillna("?"))],
                          key=lambda r: -r["n"])
    out["bias"] = sorted([{"mode": k, **_stats(g["r_multiple"])} for k, g in t.groupby("bias")], key=lambda r: -r["n"])
    # 6. trades that reached +1R and still closed at or below zero
    gb = t[(t["mfe_r"] >= 1) & (t["r_multiple"] <= 0)].sort_values("opened_ny", ascending=False)
    out["givebacks"] = [{"id": r.id, "opened": r.opened_ny.isoformat(), "symbol": r.symbol, "side": r.side, "setup": r.setup,
                         "mfe": round(float(r.mfe_r), 2), "r": round(float(r.r_multiple), 2), "exit": r.exit_reason}
                        for r in gb.head(25).itertuples()]
    out["giveback_share"] = round(float(len(gb) / len(t)), 3) if len(t) else None
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
        step = max(1, len(c) // 300)
        out["curve"] = [{"t": tc["closed_ny"].iloc[i].isoformat(), "r": round(float(cum[i]), 2)} for i in range(0, len(c), step)]
        if (len(c) - 1) % step:
            out["curve"].append({"t": tc["closed_ny"].iloc[-1].isoformat(), "r": round(float(cum[-1]), 2)})
    else:
        out["streaks"], out["curve"] = None, []
    # 8. distribution of results, and how much of the best move was kept
    edges = [-np.inf, -1.0, -0.5, -0.0001, 0.5, 1.0, 2.0, np.inf]
    labels = ["≤ −1R", "−1 to −0.5R", "−0.5 to 0", "0 to +0.5R", "+0.5 to +1R", "+1 to +2R", "> +2R"]
    hist = pd.cut(t["r_multiple"], edges, labels=labels).value_counts().reindex(labels, fill_value=0) if len(t) else pd.Series(0, index=labels)
    out["distribution"] = [{"bucket": k, "n": int(v)} for k, v in hist.items()]
    w, lo = t[t.r_multiple > 0], t[t.r_multiple <= 0]
    mf = lambda x: round(float(x.mean()), 2) if len(x) and x.notna().any() else None  # noqa: E731
    out["excursion"] = {"win_mfe": mf(w["mfe_r"]), "win_r": mf(w["r_multiple"]), "loss_mfe": mf(lo["mfe_r"]), "loss_r": mf(lo["r_multiple"]),
                        "loss_mae": mf(lo["mae_r"]), "win_mae": mf(w["mae_r"]),
                        "kept": round(float(w["r_multiple"].sum() / w["mfe_r"].clip(lower=0.01).sum()), 2) if len(w) and w["mfe_r"].notna().any() else None,
                        "reached_1r": round(float((t["mfe_r"] >= 1).mean()), 3) if len(t) else None}
    # 9. holding time
    mins = (t["closed_ny"] - t["opened_ny"]).dt.total_seconds() / 60
    hb = pd.cut(mins, [0, 15, 60, 240, np.inf], labels=["< 15 min", "15–60 min", "1–4 h", "> 4 h"], right=False)
    out["by_hold"] = [{"hold": str(k), **_stats(g["r_multiple"])} for k, g in t.groupby(hb, observed=True)]
    return out
