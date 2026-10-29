"""Were entries made before the setup's candle closed? (Oct 29 2026, Sam: "trades are taken when the set-up is identified
but the candle is not closed").

How the bot is built to work: a strategy is only scanned when the LAST 1-minute bar of its entry candle has closed
(TraderAgent.on_bar publishes `bar_signal` when (minutes since midnight + 1) is a multiple of the timeframe), on
completed candles only (BarStore.tf drops a still-forming candle), and only a signal on that just-closed candle counts.
So an entry should never be earlier than the close of its signal candle. This check verifies it on the real journals.

For every trade that recorded its setup drawing (from Oct 19 2026), the drawing's "signal bar" mark is the START of the
candle the setup fired on. That candle closes at start + timeframe. The entry time must be at or after that.

Higher-timeframe candles are a different matter: a 3m / 5m setup normally enters while the 15-minute and 1-hour
candles around it are still forming. That is by design (the setup's own candle has closed), and the report counts it
separately so the two are not confused.

    python -m fxagents.candle_check            (./fx.sh candlecheck) -> data/year_test/candle_check/report.md
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

TF_RE = re.compile(r":(\d+)(m|h)\b")


def tf_minutes(strategy: str, tf_col: str | None = None) -> int | None:
    m = TF_RE.search(str(strategy or ""))
    if m:
        return int(m.group(1)) * (60 if m.group(2) == "h" else 1)
    if tf_col:
        s = str(tf_col).replace("min", "m")
        m = re.fullmatch(r"(\d+)(m|h)", s)
        if m:
            return int(m.group(1)) * (60 if m.group(2) == "h" else 1)
    return None


def signal_bar_start(draw) -> pd.Timestamp | None:
    if isinstance(draw, str):
        try:
            draw = json.loads(draw)
        except ValueError:
            return None
    for d in draw or []:
        if d.get("role") == "signal" and d.get("t0"):
            return pd.Timestamp(d["t0"])
    return None


def check_row(r: dict) -> dict | None:
    """One trade → {early, gap_s, ...}; None when it can't be checked (no drawing, unknown timeframe)."""
    tf = tf_minutes(r.get("strategy"), r.get("tf"))
    t0 = signal_bar_start(r.get("draw"))
    if tf is None or t0 is None or not r.get("opened"):
        return None
    opened = pd.Timestamp(r["opened"])
    close = t0 + pd.Timedelta(minutes=tf)
    gap = (opened - close).total_seconds()
    # the 15-minute candle the entry fell in: still forming at entry unless the entry is exactly on its boundary
    o_ny = opened.tz_convert("America/New_York") if opened.tzinfo else opened
    m15_forming = bool(tf < 15 and o_ny.minute % 15 != 0)
    return {"id": r.get("id"), "symbol": r.get("symbol"), "strategy": r.get("strategy"), "tf_min": tf,
            "signal_bar_start": t0.isoformat(), "signal_bar_close": close.isoformat(), "opened": opened.isoformat(),
            "gap_s": gap, "early": gap < -1.0, "m15_forming": m15_forming}


def load_trades(path: Path) -> list[dict]:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    cols = {r[1] for r in db.execute("PRAGMA table_info(trades)")}
    if "draw" not in cols:
        return []
    return [dict(r) for r in db.execute("SELECT id, symbol, strategy, tf, opened, draw FROM trades WHERE opened IS NOT NULL")]


def journals(main_db: Path) -> dict[str, Path]:
    out = {}
    if main_db.exists():
        out["live"] = main_db
    for p in sorted(main_db.parent.glob(main_db.stem + "_*" + main_db.suffix)):
        out[p.stem[len(main_db.stem) + 1:]] = p
    return out


def report(rows_by_book: dict[str, list[dict]], unchecked: dict[str, int]) -> str:
    md = ["# Entry vs candle close (journals)", "",
          "Each trade's entry time against the close of the candle its setup fired on (the drawing's signal bar + the "
          "setup's timeframe). **Early** = entered before that candle closed. Trades before Oct 19 2026 have no drawing "
          "and can't be checked.", "",
          "| book | checked | entered before the setup candle closed | median delay after close | max delay | "
          "3m/5m entries while the 15m candle was still forming | not checkable |", "|---|---|---|---|---|---|---|"]
    early_rows = []
    for book, rows in rows_by_book.items():
        if not rows and not unchecked.get(book):
            continue
        g = pd.Series([r["gap_s"] for r in rows], dtype=float)
        e = [r for r in rows if r["early"]]
        early_rows += [dict(r, book=book) for r in e]
        sub15 = [r for r in rows if r["tf_min"] < 15]
        md.append(f"| {book} | {len(rows)} | **{len(e)}** | {g.median():.0f} s | {g.max():.0f} s | "
                  f"{sum(r['m15_forming'] for r in sub15)} of {len(sub15)} | {unchecked.get(book, 0)} |"
                  if len(rows) else f"| {book} | 0 | — | — | — | — | {unchecked.get(book, 0)} |")
    md.append("")
    if early_rows:
        md += ["## Entries before the setup candle closed", "", "| book | symbol | strategy | candle | closes | entered | early by |",
               "|---|---|---|---|---|---|---|"]
        for r in early_rows[:200]:
            md.append(f"| {r['book']} | {r['symbol']} | {r['strategy']} | {r['signal_bar_start'][11:16]} ({r['tf_min']}m) | "
                      f"{r['signal_bar_close'][11:16]} | {r['opened'][11:19]} | {-r['gap_s']:.0f} s |")
        md += ["", "**Some entries were made before their candle closed — this is a bug to fix.**"]
    else:
        md += ["**No entry was made before its own setup candle closed.** A 3m / 5m entry made while the 15-minute "
               "candle is still forming is how the setups are designed (their own candle has closed); whether waiting "
               "for the 15-minute close helps was tested on Oct 28 (m15_timing A: the gain came from waiting itself, a "
               "random later entry did as well)."]
    return "\n".join(md) + "\n"


def run(main_db: Path, out: Path) -> dict:
    rows_by_book, unchecked = {}, {}
    for book, p in journals(main_db).items():
        rows, n_bad = [], 0
        for r in load_trades(p):
            c = check_row(r)
            if c is None:
                n_bad += 1
            else:
                rows.append(c)
        rows_by_book[book], unchecked[book] = rows, n_bad
    out.mkdir(parents=True, exist_ok=True)
    md = report(rows_by_book, unchecked)
    (out / "report.md").write_text(md)
    summ = {b: {"checked": len(r), "early": sum(x["early"] for x in r)} for b, r in rows_by_book.items()}
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    return summ


def main(argv=None):
    from .config import load_config
    ap = argparse.ArgumentParser(description="Entries vs the close of the setup candle (Oct 29 2026)")
    ap.add_argument("--out", type=Path, default=Path("data/year_test/candle_check"))
    a = ap.parse_args(argv)
    cfg = load_config("config.yaml")
    run(Path(cfg["storage"]["db_path"]), a.out)
    print((a.out / "report.md").read_text())


if __name__ == "__main__":
    main()
