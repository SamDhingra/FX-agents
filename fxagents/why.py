"""Why did (or didn't) a book trade in a time window?   ./fx.sh why [FROM] [TO] [DAYS]

Reads both journals (real book and shadow book) and, for entries whose New York time falls between
FROM and TO (default 20:00–23:59, the Asia window) over the last DAYS days (default 2), prints:
  • trades opened
  • every signal that was seen, grouped by what happened to it (filtered / skipped / rejected) and why
  • Jev grading calls made in that window
A book with no signals at all in the window either saw no setups form, or wasn't scanning (halted or
outside its entry windows) — the 'last halt' line and the config's entry windows tell those apart.
"""
from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from pathlib import Path

import pandas as pd

from .config import load_config

NY = "America/New_York"


def _ny(s: pd.Series) -> pd.Series:
    """Journal timestamps are ISO strings, usually with a UTC offset; a naive one is New York time."""
    def one(x):
        try:
            t = pd.Timestamp(x)
        except (ValueError, TypeError):
            return pd.NaT
        return t.tz_localize(NY) if t.tzinfo is None else t.tz_convert(NY)
    return pd.to_datetime(s.map(one), utc=True).dt.tz_convert(NY)


def _in(t: pd.Series, a: str, b: str) -> pd.Series:
    m = t.dt.hour * 60 + t.dt.minute
    ah, am = map(int, a.split(":"))
    bh, bm = map(int, b.split(":"))
    lo, hi = ah * 60 + am, bh * 60 + bm
    return (m >= lo) & (m <= hi) if lo <= hi else (m >= lo) | (m <= hi)


def report(path: str, label: str, a: str, b: str, days: int) -> None:
    print(f"\n━━ {label}  ({path})")
    if not Path(path).exists():
        print("   no journal file")
        return
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    since = (pd.Timestamp.now(tz=NY) - pd.Timedelta(days=days)).tz_convert("UTC").isoformat()
    tr = pd.read_sql("SELECT opened, symbol, side, strategy, r_multiple, status FROM trades", db)
    if len(tr):
        tr["t"] = _ny(tr["opened"])
        tr = tr[(tr["t"] >= pd.Timestamp(since)) & _in(tr["t"], a, b)]
    print(f"   trades opened {a}–{b}: {len(tr)}")
    for _, r in tr.iterrows():
        print(f"     {r.t:%a %H:%M}  {r.symbol:<7} {r.side:<5} {r.strategy}  R={r.r_multiple if r.r_multiple is not None else 'open'}")
    sg = pd.read_sql("SELECT ts, symbol, strategy, action, why, quality, confidence FROM signals", db)
    if len(sg):
        sg["t"] = _ny(sg["ts"])
        sg = sg[(sg["t"] >= pd.Timestamp(since)) & _in(sg["t"], a, b)]
    print(f"   signals seen: {len(sg)}")
    if len(sg):
        c = Counter(zip(sg["action"].fillna("?"), sg["why"].fillna("").str.replace(r"[\d.$,]+", "#", regex=True)))
        for (act, why), n in c.most_common(15):
            print(f"     {n:>4} × {act:<9} {why}")
        print("   by symbol: " + ", ".join(f"{k} {v}" for k, v in sg["symbol"].value_counts().items()))
        q = sg.dropna(subset=["quality"])
        if len(q):
            print(f"   Jev grades: n={len(q)}  quality median {q.quality.median():.2f} (max {q.quality.max():.2f}), "
                  f"confidence median {q.confidence.median():.2f}")
    dc = pd.read_sql("SELECT ts, kind FROM decisions WHERE ts >= ?", db, params=((pd.Timestamp(since) - pd.Timedelta(days=1)).date().isoformat(),))
    if len(dc):
        dc["t"] = _ny(dc["ts"])
        dc = dc[_in(dc["t"], a, b)]
        print("   decisions logged: " + (", ".join(f"{k} {v}" for k, v in dc["kind"].value_counts().items()) or "none"))
    lg = pd.read_sql("SELECT ts, msg FROM learner_log ORDER BY id DESC LIMIT 200", db)
    halts = lg[lg["msg"].str.contains("KILL|halt", case=False, na=False)]
    if len(halts):
        print(f"   last halt: {halts.iloc[0].ts}  {halts.iloc[0].msg[:120]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("start", nargs="?", default="20:00")
    ap.add_argument("end", nargs="?", default="23:59")
    ap.add_argument("days", nargs="?", type=int, default=2)
    a = ap.parse_args()
    cfg = load_config()
    from .agents.setup_first import shadow_db_for, shadow_modes
    main_db = cfg["storage"]["db_path"]
    print(f"Window {a.start}–{a.end} New York, last {a.days} day(s). Entry windows in config: "
          + ", ".join("–".join(w) for w in cfg["sessions"]["entry_windows"]))
    report(main_db, f"REAL book ({cfg['selector'].get('mode', 'hourly_pick')})", a.start, a.end, a.days)
    for i, mode in enumerate(shadow_modes(cfg)):
        report(shadow_db_for(cfg, mode, i == 0), f"SHADOW book ({mode})", a.start, a.end, a.days)


if __name__ == "__main__":
    main()
