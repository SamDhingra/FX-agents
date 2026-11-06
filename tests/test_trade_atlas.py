"""Trade atlas (Nov 6 2026): the engine can keep neutral / counter-bias signals (off by default), reports slice by
setup × instrument × timeframe × hour × bias with pips, and the forward part reads every book's journal."""
import sqlite3

import numpy as np
import pandas as pd
import pytest

from fxagents import research
from fxagents import trade_atlas as A
from fxagents.journal import Journal
from tests.test_m15_timing import cfg, market, recorded  # noqa: F401  (fixture)


def _rows(cfg, monkeypatch, m1, h1, n=60, **research_extra):  # noqa: F811
    """run_job with the real filters, bias score alternating +0.9 / −0.9 by candle, min_align 0.25."""
    recorded(cfg, monkeypatch, m1, h1, n=n)              # installs the fakes (load, bias, signals, news)
    cfg["bias"]["min_align"] = 0.25
    cfg["research"] = {"only_params": {"ict_2022": {}}, **research_extra}
    return pd.DataFrame(research.run_job((cfg, "XAUUSD", "5min", ["ict_2022"])))


def test_bias_rule_and_profiles_switches(cfg, monkeypatch):  # noqa: F811
    m1, h1 = market(start="2021-03-01 00:00", days=10)
    rule = _rows(cfg, monkeypatch, m1, h1)
    off = _rows(cfg, monkeypatch, m1, h1, ignore_bias_rule=True, profiles_only=["std"])
    assert len(rule) and (rule.side * rule.bias >= 0.25).all()               # default: aligned only, as before
    assert set(rule.mgmt) > {"std"}                                          # every exit profile, as before
    assert (off.side * off.bias < 0).any() and (off.side * off.bias >= 0.25).any()
    assert set(off.mgmt) == {"std"} and (off.R_px > 0).all()
    on = off[off.side * off.bias >= 0.25]
    std = rule[rule.mgmt == "std"]
    assert len(on) == len(std) and np.allclose(on.r.to_numpy(), std.r.to_numpy())   # aligned trades identical


def test_classes():
    assert A.bias_class(1, 0.3, 0.25) == "aligned" and A.bias_class(-1, 0.3, 0.25) == "counter"
    assert A.bias_class(1, 0.1, 0.25) == "neutral" and A.bias_class(1, np.nan, 0.25) == "unknown"
    assert A.norm_bias_mode("ignored:counter") == "counter" and A.norm_bias_mode("in_doubt") == "aligned"
    assert A.norm_bias_mode("reversal_exception") == "counter" and A.norm_bias_mode("n/a") == "n/a"
    assert A.norm_bias_mode(None) == "unknown"
    assert A.session_of(21) == "Asia 20–02" and A.session_of(9) == "NY AM 08–12" and A.session_of(15) == "NY PM 12–16"


def test_history_report(cfg, monkeypatch, tmp_path):  # noqa: F811
    m1, h1 = market(start="2021-03-01 00:00", days=40)
    t = research.own_trades(_rows(cfg, monkeypatch, m1, h1, n=400, ignore_bias_rule=True, profiles_only=["std"]))
    assert len(t) > 100
    src = tmp_path / "trades"; src.mkdir()
    t.to_csv(A.job_file(src, "XAUUSD", "5min"), index=False)
    summ = A.history_report(cfg, src=src, out=tmp_path / "rep")
    assert summ["trades"] == len(t) and summ["slices"] > 0
    rep = (tmp_path / "rep/report.md").read_text()
    for s in ("## 1. Bias at entry", "aligned", "counter", "## 4. Hour of entry", "net pips", "This is a map, not a test"):
        assert s in rep
    cells = pd.read_csv(tmp_path / "rep/cells.csv")
    assert {"setup × instrument × timeframe × bias", "setup × instrument × session"} <= set(cells.slice)
    # pips = R × stop distance ÷ pip (gold 0.10)
    d = A.load_history(cfg, src)
    assert np.allclose(d.pips, d.r * d.R_px / 0.1)


def test_run_resumes_finished_jobs(cfg, tmp_path):  # noqa: F811
    hist = tmp_path / "hist"; hist.mkdir()
    pd.to_pickle(market(days=2), hist / "XAUUSD.pkl")
    out = tmp_path / "trades"; out.mkdir()
    pd.DataFrame({"r": [0.5]}).to_csv(A.job_file(out, "XAUUSD", "5min"), index=False)
    files = A.run(cfg, workers=1, out=out, hist=hist, syms=("XAUUSD",), tfs=("5min",))
    assert files == [A.job_file(out, "XAUUSD", "5min")]                          # nothing re-run


def _journal(path, rows):
    Journal(str(path))
    con = sqlite3.connect(path)
    for r in rows:
        con.execute("INSERT INTO trades(id, symbol, side, strategy, status, opened, closed, r_multiple, realized, "
                    "qty_initial, qty_gross, bias_mode) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", r)
    con.commit()
    con.close()


def test_forward_report_pools_signals_once(cfg, tmp_path):  # noqa: F811
    a = ("a1", "XAUUSD", "LONG", "sr_rejection:5m@v1", "closed", "2026-11-03T09:05:00-05:00", "2026-11-03T10:00:00-05:00",
         1.0, 100.0, 10.0, 10.0, "aligned")
    b = ("b1", "NDQ", "SHORT", "smc_mss:15m@pb-ndq", "closed", "2026-11-04T21:15:00-05:00", "2026-11-04T22:00:00-05:00",
         -1.0, -50.0, 1.0, 1.0, "ignored:counter")
    c = ("c1", "NDQ", "LONG", "c10_afternoon:5m@v2", "closed", "2026-11-04T14:00:00-05:00", "2026-11-04T15:00:00-05:00",
         2.0, 80.0, 1.0, 1.0, "n/a")
    _journal(tmp_path / "p.sqlite", [a, c])
    _journal(tmp_path / "s.sqlite", [a[:0] + ("a2",) + a[1:], b])            # the same signal in a second book
    summ = A.forward_report(cfg, out=tmp_path / "f", book_list=[("practice", str(tmp_path / "p.sqlite")),
                                                                ("playbook_nobias", str(tmp_path / "s.sqlite"))])
    assert summ["trades"] == 4 and summ["pooled"] == 3
    rep = (tmp_path / "f/report.md").read_text()
    assert "counter" in rep and "n/a" in rep and "Playbook, no bias rule" in rep
    t = A.load_forward(cfg, [("practice", str(tmp_path / "p.sqlite"))])
    mult = float(cfg["instruments"]["XAUUSD"].get("multiplier", 1))          # as the dashboard: $ ÷ ($ per pip × units)
    assert t.loc[t.id == "a1", "pips"].iloc[0] == pytest.approx(100.0 / (mult * 0.1 * 10.0))
