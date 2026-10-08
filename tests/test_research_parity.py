"""Research ↔ live parity and research-method fixes from the Oct 2026 audit (docs/astra_audit_2026-10-08.md):
F08 trend exits, F09 bias weights, F16 busy-state suppression, F17 report mandate/window/units, F18 lab
promotion + timeless pins, F22 FOMC dates, F24 selection outcome availability, F25 bias metadata, the
day-block bootstrap interval, the lab out-of-sample window and the run manifest."""
from __future__ import annotations

import copy
import json
import subprocess
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from fxagents import lab, playbook as P, research, year_test
from fxagents.config import load_config

TZ = "America/New_York"


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("FX_NO_LOCAL_CONFIG", "1")
    c = load_config()
    c["storage"] = {**c["storage"], "db_path": str(tmp_path / "journal.sqlite")}
    c["history_dir"] = str(tmp_path / "history")
    c["research_dir"] = str(tmp_path / "research")
    c["playbook"] = {}
    return c


# ── F08: trend = partial at 2R + runner, no adds (live RiskAgent mgmt "trend") ──
def _path(points):
    """1m bars through the given closes; each bar's range spans the previous and current close."""
    C = np.array(points, float)
    O = np.r_[C[0], C[:-1]]
    return O, np.maximum(O, C), np.minimum(O, C), C


def test_trend_profile_banks_partial_and_trails_runner_like_live(cfg):
    # entry 100, stop 99 (R=1): up to 2R, on to 5R, then a slide back to entry
    O, H, L, C = _path([100, 101, 102, 103, 104, 105, 104.5, 104.0, 103.0, 101.0, 100.0])
    n = len(C)
    m = research.mgmt_profiles(cfg, "15min")["trend"]
    res = research.simulate_live(O, H, L, C, np.arange(n), 0, 1, 99.0, m, 0.0, np.zeros(n, bool), None, 480.0,
                                 full_exit=research.full_exit(cfg, "trend"))
    # half banked at 2R, the runner stopped at the trailed level (5R reached → stop 4.1R): 0.5×2 + 0.5×4.1
    assert res["exit_reason"] != "target" and res["adds"] == 0
    assert res["r"] == pytest.approx(3.05)
    # scalp / tpX still close everything at the first target; with pyramiding globally off, so does trend (live)
    assert research.full_exit(cfg, "scalp") and research.full_exit(cfg, "tp1.5") and not research.full_exit(cfg, "std")
    off = copy.deepcopy(cfg)
    off["management"]["pyramid"]["enabled"] = False
    assert research.full_exit(off, "trend")


def test_std_profile_honours_max_adds(cfg):
    O, H, L, C = _path([100, 101, 102, 103, 104, 105, 104.5, 104.0, 103.0, 101.0, 100.0])
    n = len(C)
    cfg["management"]["pyramid"].update(enabled=True, max_adds=0)
    m = research.mgmt_profiles(cfg, "15min")["std"]
    assert not m.pyramid
    m.add_mode = "step"
    res = research.simulate_live(O, H, L, C, np.arange(n), 0, 1, 99.0, m, 0.0, np.zeros(n, bool), None, 480.0, False)
    assert res["adds"] == 0
    cfg["management"]["pyramid"]["max_adds"] = 2
    assert research.mgmt_profiles(cfg, "15min")["std"].pyramid


# ── run_job on a controlled market: F09 weights, F25 per-trade bias, F16 busy candidates ──
def _market():
    idx = pd.date_range("2026-07-06 00:00", "2026-07-10 16:59", freq="1min", tz=TZ)
    idx = idx[idx.hour != 17]
    k = np.arange(len(idx))
    c = 2000 + 0.5 * np.sin(k / 30.0)             # never reaches +1R on a 5-point stop: trades run to time exits
    m1 = pd.DataFrame({"open": np.r_[c[0], c[:-1]], "close": c}, index=idx)
    m1["high"], m1["low"], m1["volume"] = m1[["open", "close"]].max(axis=1) + 0.05, m1[["open", "close"]].min(axis=1) - 0.05, 1.0
    h1 = m1.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return m1[["open", "high", "low", "close", "volume"]], h1


@pytest.fixture()
def job(cfg, monkeypatch):
    m1, h1 = _market()
    seen = {}

    def fake_bias(h1_, when, close_at_when=None, weights=None):
        seen["weights"] = weights
        return pd.DataFrame({"score": 0.3 + 0.001 * np.arange(len(when))}, index=when)   # differs bar to bar

    def fake_signals(st, df, ctx):
        ix = [df.index.get_loc(pd.Timestamp(f"2026-07-07 {hm}", tz=TZ)) for hm in ("09:00", "09:15", "13:45")]
        return [SimpleNamespace(i=i, side=1, stop=float(df["close"].iloc[i]) - 5.0) for i in ix]

    monkeypatch.setattr(research, "load", lambda cfg_, sym: (m1, h1))
    monkeypatch.setattr(research, "bias_frame", fake_bias)
    monkeypatch.setattr(research, "_signals", fake_signals)
    cfg["bias"]["weights"] = {"d": 0.0, "h4": 0.0, "h1": 1.0}                 # an H1-only override
    cfg["research"] = {"only_params": {"ict_2022": {}}}
    rows = pd.DataFrame(research.run_job((cfg, "XAUUSD", "15min", ["ict_2022"])))
    return rows, seen


def test_research_bias_uses_configured_weights(job):
    _, seen = job
    assert seen["weights"] == {"d": 0.0, "h4": 0.0, "h1": 1.0}


def test_research_stores_each_trades_own_bias(job):
    rows, _ = job
    std = rows[rows["mgmt"] == "std"].sort_values("ts")
    assert std["bias"].nunique() == len(std) == 3                     # not the last filtered signal's score


def test_research_keeps_busy_candidates_flagged(job):
    rows, _ = job
    std = rows[rows["mgmt"] == "std"].sort_values("ts")
    # 09:15 entry runs to the 4 h max hold; the 09:30 signal is kept (flagged), the 14:00 one is free again
    assert list(std["busy_self"]) == [False, True, False]
    assert len(research.own_trades(std)) == 2 and "exit_ts" in std.columns


# ── F16: the portfolio applies occupancy only to ACCEPTED positions ──
def test_rejected_trade_does_not_block_its_cells_later_signal():
    d = pd.Timestamp("2026-08-04").date()
    t = lambda hm: pd.Timestamp(f"2026-08-04 {hm}", tz=TZ)  # noqa: E731
    row = dict(variant="default", mgmt="std", tf="5min", side=1, day=d, r=1.0, bars=3, e=0.1, cost_r=0.05)
    rows = [dict(row, sym="NDQ", setup="a", ts=t("09:50"), exit_ts=t("10:05"), p=0.6, busy_self=False),
            dict(row, sym="US30", setup="b", ts=t("10:00"), exit_ts=t("10:30"), p=0.6, busy_self=False),   # rejected: index cap
            dict(row, sym="US30", setup="b", ts=t("10:10"), exit_ts=t("10:40"), p=0.6, busy_self=True)]   # B's own trade "open"
    pf = P.portfolio(pd.DataFrame(rows), P.Policy())
    assert [(r.sym, r.ts.strftime("%H:%M")) for r in pf.itertuples()] == [("NDQ", "09:50"), ("US30", "10:10")]
    # the cell's own statistics still count one trade at a time; the candidate stream keeps all three
    cube = P.CellCube(pd.DataFrame(rows))
    st = cube.window(0, len(cube.days))
    assert st.loc[st["setup"] == "b", "n"].iloc[0] == 1 and len(cube.trades) == 3


# ── F24: selection only counts outcomes known at the cutoff ──
def test_selection_ignores_trades_still_open_at_the_cutoff():
    days = [d.date() for d in pd.bdate_range("2026-07-06", periods=40)]
    base = dict(sym="XAUUSD", tf="5min", setup="smc_bos_retest", variant="default", mgmt="std", side=1, bars=6, cost_r=0.05)
    rows = [dict(base, ts=pd.Timestamp(d, tz=TZ) + pd.Timedelta(hours=10), day=d, r=1.0,
                 exit_ts=pd.Timestamp(d, tz=TZ) + pd.Timedelta(hours=10, minutes=30)) for d in days]
    b = 30
    clean = P.CellCube(pd.DataFrame(rows)).window(b - 20, b)
    # entered on the last day before the cutoff, exits two days later with a big loss
    late = dict(base, ts=pd.Timestamp(days[b - 1], tz=TZ) + pd.Timedelta(hours=15), day=days[b - 1], r=-50.0,
                exit_ts=pd.Timestamp(days[b + 1], tz=TZ) + pd.Timedelta(hours=10))
    cube = P.CellCube(pd.DataFrame(rows + [late]))
    st = cube.window(b - 20, b)
    assert st["n"].iloc[0] == clean["n"].iloc[0] and st["sum_r"].iloc[0] == clean["sum_r"].iloc[0]
    assert len(P.select(st, P.Policy())) == len(P.select(clean, P.Policy()))
    assert cube.window(b - 20, b + 2)["n"].iloc[0] == 23                 # 22 days + the late one, once it has exited
    assert cube.window(b - 20, b, cutoff=days[b + 1])["n"].iloc[0] == 20  # exit day itself is not before the cutoff


# ── report statistics: day-block bootstrap interval, not "chance it's really ≤ 0" ──
def test_summary_reports_day_block_interval():
    days = [d.date() for d in pd.bdate_range("2026-07-06", periods=20)]
    rows = []
    for k, d in enumerate(days):                                       # 13 good days, 7 bad, 10 identical trades each
        for j in range(10):
            rows.append({"ts": pd.Timestamp(d, tz=TZ) + pd.Timedelta(hours=9, minutes=j), "day": d,
                         "r": 1.0 if k % 3 else -1.0})
    s = P.summarize(pd.DataFrame(rows), "r")
    lo, hi = s["avg_ci95"]
    assert lo < 0 < hi                         # 20 independent days of evidence, not 200 independent trades
    assert "day-block" in s["ci_method"]


# ── F17: walk-forward on the original mandate, actual window + units, sums reconcile ──
def _trades(sym, setup, days, wr=0.62):
    out, seq = [], 0
    for d in days:
        win = int((seq + 1) * wr) > int(seq * wr)
        seq += 1
        ts = pd.Timestamp(d, tz=TZ) + pd.Timedelta(hours=9, minutes=40)
        r = 1.0 if win else -1.0
        out.append({"sym": sym, "tf": "5min", "setup": setup, "variant": "default", "mgmt": "std", "ts": ts, "day": d,
                    "exit_ts": ts + pd.Timedelta(minutes=30), "r": r, "w": 0.5, "rw": 0.5 * r, "cost_r": 0.05,
                    "bars": 6, "exit": "x", "side": 1, "hour": 9, "busy_self": False})
    return out


def test_year_test_trades_only_the_mandate_and_report_reconciles(cfg, tmp_path):
    days = [d.date() for d in pd.bdate_range("2026-07-06", periods=60)]
    t = pd.DataFrame(_trades("XAUUSD", "smc_bos_retest", days) + _trades("EURUSD", "smc_bos_retest", days))
    out = tmp_path / "research"
    out.mkdir()
    t.to_pickle(out / "trades.pkl")
    cfg["playbook"] = {"window_days": 30}
    assert cfg["instruments"]["EURUSD"].get("trade") is False           # watch-only in config.yaml
    mandate = [s for s, ic in cfg["instruments"].items() if ic.get("trade", True) is not False]
    research_cfg = copy.deepcopy(cfg)
    for s in research_cfg["instruments"]:
        research_cfg["instruments"][s]["trade"] = True                  # what the year test does for research
    summary = P.build(year_test.execution_cfg(research_cfg, mandate), robustness=False)
    wf = summary["walk_forward"]
    assert wf["summary"]["trades"] > 0 and "EURUSD" not in {x["sym"] for x in wf["trades"]}
    assert sum(w["r"] for w in wf["weekly"]) == pytest.approx(wf["summary"]["sum_r"], abs=0.01)
    assert wf["units"] == "rw" and wf["summary"]["units"] == "rw"
    txt = year_test.write_report(tmp_path, t, year_test.cell_table(t), summary, 60, cfg)
    assert "30 observed trade days" in txt and "trailing 60" not in txt and "chance it's really" not in txt
    assert "day-block bootstrap" in txt and "**rw**" in txt


# ── F18: lab promotion gate, explicit force, effective_from ──
def _lab_trades(rs, start="2026-07-01"):
    ts = pd.date_range(start, periods=len(rs), freq="6h", tz=TZ)
    return pd.DataFrame([{"sym": "XAUUSD", "tf": "15min", "mgmt": "std", "ts": x, "r": r, "cost_r": 0.05}
                         for x, r in zip(ts, rs)])


def test_promote_refuses_unscreened_or_unmatched_cells_unless_forced(cfg):
    c = lab.add(cfg, "trend_pullback", {"ema": 50}, ["XAUUSD"], ["15min"], "test")
    cells = lab.verdict(_lab_trades([1.0, -1.0, 1.0, 1.0] * 15))      # 60 trades: screened, not promotable
    assert cells[0]["screened"] and not cells[0]["promotable"]
    lab.update(cfg, c["id"], status="screened", results={"cells": cells, "screened": True})
    with pytest.raises(ValueError):
        lab.promote(cfg, c["id"])
    with pytest.raises(ValueError):
        lab.promote(cfg, c["id"], [{"sym": "XAUUSD", "tf": "15min", "mgmt": "std"}])      # explicit, still gated
    with pytest.raises(ValueError):
        lab.promote(cfg, c["id"], [{"sym": "NDQ", "tf": "5min", "mgmt": "std"}])          # never tested
    got = lab.promote(cfg, c["id"], force=True)
    assert got["forced"] is True
    pin = lab.lab_pinned(cfg)[0]
    assert pin["forced"] is True and pin["effective_from"] and pin["evidence"]["n"] == 60
    # a 2x-cost stress that kills the edge blocks promotion even with plenty of trades
    thin = lab.verdict(_lab_trades([0.06, -0.04] * 100).assign(cost_r=0.2))
    assert thin[0]["n"] == 200 and not thin[0]["promotable"]


def test_pins_apply_only_from_their_effective_date(cfg):
    c = lab.add(cfg, "trend_pullback", {"ema": 50}, ["XAUUSD"], ["15min"], "test")
    cells = lab.verdict(_lab_trades([1.0, -1.0, 1.0, 1.0] * 30))
    lab.update(cfg, c["id"], status="screened", results={"cells": cells, "screened": True})
    lab.promote(cfg, c["id"])
    ef = pd.Timestamp(lab.lab_pinned(cfg)[0]["effective_from"])
    before = (ef - pd.Timedelta(days=30)).date()
    assert P.with_pinned(cfg, {"cells": []}, asof=before)["cells"] == []                     # replay before promotion
    assert P.with_pinned(cfg, {"cells": []}, asof=ef - pd.Timedelta(minutes=1))["cells"] == []
    assert len(P.with_pinned(cfg, {"cells": []}, asof=ef + pd.Timedelta(minutes=1))["cells"]) == 1
    assert len(P.with_pinned(cfg, {"cells": []})["cells"]) == 1                              # now


# ── lab out-of-sample window (--from / --until) + manifest ──
def test_lab_run_restricts_history_and_records_window(cfg, monkeypatch, tmp_path):
    hd = tmp_path / "history"
    hd.mkdir()
    m1, h1 = _market()
    pd.to_pickle((m1, h1), hd / "XAUUSD.pkl")
    seen = {}

    def fake_run_all(cfg_, syms, tfs, classes, workers=1):
        m, _ = pd.read_pickle(research.history_dir(cfg_) / "XAUUSD.pkl")
        seen["last"] = m.index.max()
        ts = pd.date_range("2026-07-06 10:00", periods=4, freq="1D", tz=TZ)
        return pd.DataFrame({"sym": "XAUUSD", "tf": "15min", "mgmt": "std", "ts": ts, "r": [1.0, -1.0, 1.0, 1.0],
                             "cost_r": 0.05, "day": [x.date() for x in ts]})

    monkeypatch.setattr(research, "run_all", fake_run_all)
    c = lab.add(cfg, "trend_pullback", {}, ["XAUUSD"], ["15min"], "oos")
    got = lab.run(cfg, c["id"], since="2026-07-07", until="2026-07-08")
    assert got["status"] in ("screened", "failed"), got.get("error")
    assert seen["last"] < pd.Timestamp("2026-07-09", tz=TZ)                                    # nothing after --until
    res = got["results"]
    assert res["window"] == {"from": "2026-07-07", "until": "2026-07-08"} and res["trades"] == 3
    assert res["span"][0] == "2026-07-07"
    man = res["manifest"]
    assert man["git_sha"] and len(man["config_sha256"]) == 16 and man["data_span"]["from"].startswith("2026-07-07")


def test_manifest_sha_fallback_and_secret_free_config_hash(cfg, monkeypatch):
    def boom(*a, **k):
        raise OSError("no git")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setenv("FX_GIT_SHA", "abc123")
    assert research.git_sha() == "abc123"
    monkeypatch.delenv("FX_GIT_SHA")
    assert research.git_sha() == "unknown"
    h = research.config_hash(cfg)
    other = {**cfg, "oanda": {"token": "secret"}, "telegram": {"token": "x"}}
    assert research.config_hash(other) == h
    changed = copy.deepcopy(cfg)
    changed["management"]["rr_initial"] = 1.5
    assert research.config_hash(changed) != h
    json.dumps(research.manifest(cfg), default=str)


# ── F22: FOMC days of the years the long tests cover ──
def test_news_block_knows_fomc_2024_and_2025():
    for d in ("2024-01-31", "2024-12-18", "2025-03-19", "2025-12-10", "2026-09-16"):
        assert research.news_block(pd.Timestamp(f"{d} 14:00", tz=TZ)), d
    assert not research.news_block(pd.Timestamp("2025-03-12 14:00", tz=TZ))
