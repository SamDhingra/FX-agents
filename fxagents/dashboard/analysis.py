"""Analysis page (Nov 4 2026, Sam: "to do the analysis we have to go through lot of hoops"). One request answers what
used to take a diagnostic run: per setup × instrument scorecard, why signals were not taken (by reason), results by
hour and weekday, exits, bias relation and the trades that gave back +1R. Read-only, per book, over a range of days.
"""
from __future__ import annotations

import re
from collections import defaultdict

import pandas as pd

NY = "America/New_York"

# signal refusal text → a reason anyone can read at a glance (order matters: first match wins)
REASONS = [
    ("Bias rule", r"bias|counter-bias|counter to"),
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


def reason_of(why: str | None) -> str:
    w = (why or "").lower()
    for name, pat in REASONS:
        if re.search(pat, w):
            return name
    return "Other"


def setup_of(strategy: str | None) -> str:
    """'sr_rejection:30m@pb-us30-d-trend' → 'sr_rejection'; 'c10_afternoon:5m@v2' → 'c10_afternoon'."""
    return str(strategy or "?").split(":")[0].split("@")[0]


def _ny(s: pd.Series) -> pd.Series:
    t = pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    return t.dt.tz_convert(NY)


def _stats(r: pd.Series) -> dict:
    r = r.dropna()
    n = len(r)
    if not n:
        return {"n": 0, "win": None, "avg": None, "sum": 0.0}
    return {"n": int(n), "win": round(float((r > 0).mean()), 3), "avg": round(float(r.mean()), 3), "sum": round(float(r.sum()), 2)}


def build(db, days: int = 30, now: pd.Timestamp | None = None) -> dict:
    now = now if now is not None else pd.Timestamp.now(tz=NY)
    since = now - pd.Timedelta(days=days)
    t = pd.read_sql_query("SELECT id, symbol, side, strategy, opened, closed, r_multiple, mfe_r, mae_r, exit_reason, bias_mode, "
                          "realized FROM trades WHERE status='closed' AND r_multiple IS NOT NULL", db)
    t["opened_ny"] = _ny(t["opened"])
    t = t[t["opened_ny"] >= since].copy()
    t["setup"] = t["strategy"].map(setup_of)
    sig = pd.read_sql_query("SELECT ts, symbol, strategy, side, action, why FROM signals", db)
    sig["ts_ny"] = _ny(sig["ts"])
    sig = sig[sig["ts_ny"] >= since].copy()
    sig["setup"] = sig["strategy"].map(setup_of)
    sig["reason"] = [("Taken" if a == "taken" else reason_of(w)) for a, w in zip(sig["action"], sig["why"])]

    out: dict = {"days": days, "since": since.isoformat(), "totals": _stats(t["r_multiple"]),
                 "pnl": round(float(t["realized"].fillna(0).sum()), 2)}
    # 1. scorecard: setup × instrument (with what happened to its signals)
    rows = []
    fun = sig.groupby(["setup", "symbol"])["reason"].value_counts().unstack(fill_value=0) if len(sig) else pd.DataFrame()
    keys = set(map(tuple, t[["setup", "symbol"]].drop_duplicates().to_numpy())) | set(fun.index.tolist())
    for setup, sym in sorted(keys):
        g = t[(t.setup == setup) & (t.symbol == sym)]
        st = _stats(g["r_multiple"])
        give = int(((g["mfe_r"] >= 1) & (g["r_multiple"] <= 0)).sum()) if "mfe_r" in g else 0
        f = fun.loc[(setup, sym)].to_dict() if (setup, sym) in fun.index else {}
        refused = {k: int(v) for k, v in sorted(f.items(), key=lambda kv: -kv[1]) if k != "Taken" and v}
        last = g["opened_ny"].max() if len(g) else None
        rows.append({"setup": setup, "symbol": sym, **st, "givebacks": give,
                     "avg_mfe": round(float(g["mfe_r"].mean()), 2) if len(g) and g["mfe_r"].notna().any() else None,
                     "signals": int(sum(f.values())), "taken": int(f.get("Taken", 0)), "refused": refused,
                     "last": last.isoformat() if last is not None and pd.notna(last) else None})
    out["scorecard"] = sorted(rows, key=lambda r: (-(r["sum"] or 0), r["setup"]))
    # 2. why signals were not taken (whole book)
    out["refusals"] = [{"reason": k, "n": int(v)} for k, v in sig[sig.reason != "Taken"]["reason"].value_counts().items()]
    out["signals"] = {"seen": int(len(sig)), "taken": int((sig.reason == "Taken").sum())}
    # 3. by hour and weekday (New York, entry time)
    out["by_hour"] = [{"hour": int(h), **_stats(g["r_multiple"])} for h, g in t.groupby(t["opened_ny"].dt.hour)]
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    out["by_weekday"] = [{"day": names[int(d)], **_stats(g["r_multiple"])} for d, g in t.groupby(t["opened_ny"].dt.dayofweek)]
    # 4. exits
    out["exits"] = sorted([{"reason": str(k or "?"), **_stats(g["r_multiple"])} for k, g in t.groupby(t["exit_reason"].fillna("?"))],
                          key=lambda r: -r["n"])
    # 5. bias relation (aligned / counter / ignored:<what the rule would have said>)
    bm = t["bias_mode"].fillna("—").astype(str)
    out["bias"] = sorted([{"mode": k, **_stats(g["r_multiple"])} for k, g in t.groupby(bm)], key=lambda r: -r["n"])
    # 6. trades that reached +1R and still closed at or below zero
    gb = t[(t["mfe_r"] >= 1) & (t["r_multiple"] <= 0)].sort_values("opened_ny", ascending=False)
    out["givebacks"] = [{"id": r.id, "opened": r.opened_ny.isoformat(), "symbol": r.symbol, "side": r.side, "setup": r.setup,
                         "mfe": round(float(r.mfe_r), 2), "r": round(float(r.r_multiple), 2), "exit": r.exit_reason}
                        for r in gb.head(25).itertuples()]
    out["giveback_share"] = round(float(len(gb) / len(t)), 3) if len(t) else None
    # 7. streaks and drawdown in R (closed order)
    c = t.sort_values("closed")["r_multiple"].to_numpy()
    if len(c):
        cum = c.cumsum()
        dd = float((cum - pd.Series(cum).cummax().clip(lower=0).to_numpy()).min())
        best = worst = cur = 0
        for x in c:
            cur = cur + 1 if x > 0 and cur >= 0 else (cur - 1 if x <= 0 and cur <= 0 else (1 if x > 0 else -1))
            best, worst = max(best, cur), min(worst, cur)
        out["streaks"] = {"max_dd_r": round(dd, 2), "longest_win": best, "longest_loss": -worst, "current": int(cur)}
    else:
        out["streaks"] = None
    return out
