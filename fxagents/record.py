"""Closed-trade record per book and strategy for one instrument, as a Markdown table (for sharing / pasting).

  python -m fxagents.record XAUUSD        (./fx.sh record XAUUSD)
Reads every journal*.sqlite in the data folder: journal.sqlite = the live book, journal_<mode>.sqlite = shadow books.
"""
from __future__ import annotations

import glob
import os
import sqlite3
import sys


def table(symbol: str, data_dir: str) -> str:
    out = [f"| Book | Strategy | Trades | Win rate | Avg R | Total R | P&L $ | First – last |",
           "|---|---|---|---|---|---|---|---|"]
    for f in sorted(glob.glob(os.path.join(data_dir, "journal*.sqlite"))):
        book = os.path.basename(f)[len("journal"):-len(".sqlite")].strip("_") or "live"
        try:
            rows = sqlite3.connect(f).execute(
                "SELECT strategy, COUNT(*), AVG(realized > 0), AVG(r_multiple), SUM(r_multiple), SUM(realized), "
                "MIN(substr(opened, 1, 10)), MAX(substr(opened, 1, 10)) FROM trades "
                "WHERE symbol = ? AND status = 'closed' GROUP BY 1 ORDER BY 2 DESC", (symbol,)).fetchall()
        except sqlite3.Error:
            continue
        for s, n, w, a, t, p, d0, d1 in rows:
            out.append(f"| {book} | {s} | {n} | {w:.0%} | {a or 0:+.3f} | {t or 0:+.2f} | {p or 0:+,.0f} | {d0} – {d1} |")
    return "\n".join(out) if len(out) > 2 else f"No closed {symbol} trades in {data_dir}."


if __name__ == "__main__":
    print(table(sys.argv[1] if len(sys.argv) > 1 else "XAUUSD",
                os.path.dirname(os.environ.get("FX_DB_PATH", "data/journal.sqlite"))))
