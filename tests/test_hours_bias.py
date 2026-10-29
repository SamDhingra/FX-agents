"""All-hours / no-bias playbook test (registered Oct 29 2026): tagging, gates, one-shot and vault rules. No data needed."""
import json

import numpy as np
import pandas as pd
import pytest

from fxagents import hours_bias_test as HB
from fxagents.config import load_config

TZ = "America/New_York"


def fake_trades(n_days=400, seed=1):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2021-01-04", periods=n_days, tz=TZ)
    rows = []
    for d in days:
        for hm, side, bias, r in ((9 * 60 + 15, 1, 0.6, 0.0), (6 * 60, 1, 0.6, 0.0), (9 * 60 + 40, 1, -0.6, 0.0),
                                  (12 * 60, -1, 0.1, 0.0), (1 * 60, 1, -0.5, 0.0)):
            rows.append({"ts": d + pd.Timedelta(minutes=hm), "side": side, "bias": bias, "r": r, "cost_r": 0.05,
                         "day": d.date()})
    t = pd.DataFrame(rows)
    g = HB.tag(t, load_config("config.yaml"))
    # H earns +0.5R, B loses, base is flat with noise
    t["r"] = np.where(g.group == "H", 0.5, np.where(g.group == "B", -0.3, 0.0)) + rng.normal(0, 0.05, len(t))
    return t


def test_tagging_follows_todays_windows_and_bias():
    t = fake_trades(3)
    g = HB.tag(t, load_config("config.yaml"))
    by = dict(zip(pd.to_datetime(g.ts).dt.strftime("%H:%M"), g.group))
    assert by["09:15"] == "base" and by["06:00"] == "H" and by["09:40"] == "B"
    assert by["12:00"] == "neither"                      # outside windows and neutral: neither question
    assert by["01:00"] == "neither"                      # outside windows and counter
    assert set(g[g.group == "H"].block) == {"05:00–08:30"}
    assert HB.relaxed_cfg(load_config("config.yaml"))["sessions"]["entry_windows"] == [["20:00", "23:59"], ["00:00", "15:50"]]


def test_seen_run_judges_only_the_clean_years_and_runs_once(tmp_path, monkeypatch):
    cfg = load_config("config.yaml")
    trades = fake_trades(1300)                            # into 2026: the picked year must not count
    runner = lambda c, cells, hist, w: {"x:5m@a": trades}
    out = tmp_path / "seen"
    s = HB.run("seen", [{"id": "x:5m@a", "sym": "XAUUSD"}], cfg, 1, out, tmp_path / "h", runner=runner)
    assert s["H"]["pass"] and not s["B"]["pass"]
    clean = pd.to_datetime(trades.ts).dt.tz_localize(None) < HB.CLEAN_END
    g = HB.tag(trades, cfg)
    assert s["H"]["n"] == int(((g.group == "H") & clean).sum())
    rep = (out / "report.md").read_text()
    assert "./fx.sh hoursbias vault" in rep and "Oct 8 2025 → Sep 2026" in rep
    with pytest.raises(SystemExit):
        HB.run("seen", [{"id": "x:5m@a", "sym": "XAUUSD"}], cfg, 1, out, tmp_path / "h", runner=runner)
    # the vault only takes the group that passed
    monkeypatch.setitem(HB.OUT, "seen", out)
    seen_calls = []
    def vr(c, cells, hist, w):
        seen_calls.append(c["bias"]["min_align"])
        return {"x:5m@a": fake_trades(300, seed=2)}
    v = HB.run("vault", [{"id": "x:5m@a", "sym": "XAUUSD"}], cfg, 1, tmp_path / "vault", tmp_path / "h", runner=vr)
    assert set(v) >= {"H"} and "B" not in v and seen_calls == [-9.0]
    assert "Verdict on 2016–2020" in (tmp_path / "vault" / "report.md").read_text()


def test_vault_refuses_without_a_seen_pass(tmp_path, monkeypatch):
    monkeypatch.setitem(HB.OUT, "seen", tmp_path / "none")
    with pytest.raises(SystemExit):
        HB.run("vault", [], load_config("config.yaml"), 1, tmp_path / "v", tmp_path / "h", runner=lambda *a: {})
