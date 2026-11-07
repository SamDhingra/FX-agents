"""Analysis page data: scorecard with signal outcomes, refusal reasons, hours, exits, bias, givebacks."""
import pandas as pd
from fastapi.testclient import TestClient

from fxagents.dashboard import analysis as A
from fxagents.dashboard.server import build_app
from fxagents.journal import Journal
from tests.test_dashboard_insights import make_ctx


def _journal(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    rows = [("a", "US30", "sr_rejection:30m@pb-us30-d-trend", "2026-11-02T10:30:00-05:00", "2026-11-02T12:00:00-05:00", 1.5, 1.8, "target", "aligned"),
            ("b", "US30", "sr_rejection:30m@pb-us30-d-trend", "2026-11-03T10:30:00-05:00", "2026-11-03T11:00:00-05:00", -1.0, 1.34, "stop", "ignored:counter"),
            ("c", "NDQ", "smc_mss:5m@pb-ndq-d", "2026-11-03T14:00:00-05:00", "2026-11-03T14:30:00-05:00", -1.0, 0.2, "stop", "aligned")]
    for i, sym, st, op, cl, r, mfe, ex, bm in rows:
        j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple,mfe_r,exit_reason,bias_mode,realized) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (i, sym, "SHORT", st, "closed", op, cl, r, mfe, ex, bm, r * 100))
    j.db.commit()
    for ts, why, act in (("2026-11-03T09:00", "counter to BEARISH bias", "filtered"), ("2026-11-03T15:45", "outside entry windows", "rejected"),
                         ("2026-11-03T14:25", "index group full (one index position per direction at a time)", "rejected"),
                         ("2026-11-02T10:30", None, "taken")):
        j.add_signal({"ts": ts, "symbol": "US30", "strategy": "sr_rejection:30m@pb-us30-d-trend", "side": "SHORT", "entry": 1, "stop": 2,
                      "action": act, "why": why})
    return j


def test_build(tmp_path):
    j = _journal(tmp_path)
    out = A.build(j.db, days=30, now=pd.Timestamp("2026-11-04 12:00", tz="America/New_York"))
    assert out["totals"]["n"] == 3 and out["pnl"] == -50.0
    sr = next(r for r in out["scorecard"] if r["setup"] == "sr_rejection" and r["symbol"] == "US30")
    assert sr["n"] == 2 and sr["givebacks"] == 1 and sr["signals"] == 4 and sr["taken"] == 1
    assert sr["refused"] == {"Bias rule": 1, "Outside entry window": 1, "Position limits": 1}
    assert {r["reason"] for r in out["refusals"]} == {"Bias rule", "Outside entry window", "Position limits"}
    assert out["givebacks"][0]["id"] == "b" and out["giveback_share"] == round(1 / 3, 3)
    assert {b["mode"] for b in out["bias"]} == {"aligned", "ignored:counter"}
    assert out["streaks"]["longest_loss"] == 2 and out["streaks"]["max_dd_r"] == -2.0


def test_endpoint(tmp_path):
    ctx = make_ctx(tmp_path)
    r = TestClient(build_app(ctx)).get("/api/analysis?days=3650").json()
    assert "scorecard" in r and "refusals" in r and "by_hour" in r


def test_filters_and_new_sections(tmp_path):
    j = _journal(tmp_path)
    now = pd.Timestamp("2026-11-04 12:00", tz="America/New_York")
    out = A.build(j.db, days=30, now=now, filters={"symbol": "US30"})
    assert out["totals"]["n"] == 2 and {r["symbol"] for r in out["scorecard"]} == {"US30"}
    assert set(out["options"]["symbol"]) == {"US30", "NDQ"} and out["options"]["profile"] == ["standard", "trend"]
    assert out["by_profile"][0]["profile"] == "trend" and out["by_tf"][0]["tf"] == "30m"
    assert [s["session"] for s in out["by_session"]] == ["New York"]
    assert out["curve"][-1]["r"] == 0.5 and sum(d["n"] for d in out["distribution"]) == 2
    assert out["excursion"]["reached_1r"] == 1.0
    o2 = A.build(j.db, days=30, now=now, filters={"setup": "smc_mss", "side": "SHORT", "tf": "5m", "profile": "standard"})
    assert o2["totals"]["n"] == 1 and o2["signals"]["seen"] == 0
    assert A.build(j.db, days=30, now=now, filters={"bias": "ignored:counter"})["totals"]["n"] == 1
    assert A.session_of(19) == "Asia" and A.session_of(2) == "Asia" and A.session_of(5) == "London" and A.session_of(10) == "New York"
    assert A.profile_of("dtfx_close_fib:15m@pb-us30-15ba-trend") == "trend" and A.tf_of("c10_afternoon:5m@v2") == "5m"


def test_pips(tmp_path):
    from fxagents import units
    from fxagents.config import load_config
    cfg = load_config("config.yaml")
    j = Journal(str(tmp_path / "p.sqlite"))
    rows = [("w1", 300.0, 1.5), ("w2", 200.0, 1.0), ("l1", -100.0, -1.0), ("l2", -100.0, -1.0), ("l3", -100.0, -1.0)]
    for i, (tid, pnl, r) in enumerate(rows):
        j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple,realized,qty_initial,qty_gross) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (tid, "US30", "LONG", "sr_rejection:30m@pb-us30-d", "closed",
                                                       f"2026-11-0{i + 1}T10:00:00-05:00", f"2026-11-0{i + 1}T11:00:00-05:00", r, pnl, 2.0, 2.0))
    j.db.commit()
    out = A.build(j.db, days=30, now=pd.Timestamp("2026-11-06 12:00", tz="America/New_York"), cfg=cfg)
    per = 1 / (float(cfg["instruments"]["US30"]["multiplier"]) * units.pip_size(cfg, "US30") * 2.0)   # pips per $1
    T = out["totals"]
    assert T["pips"] == round(200 * per, 1) and T["win_pips"] == round(250 * per, 1) and T["loss_pips"] == round(-100 * per, 1)
    assert T["payoff"] == 2.5 and T["win"] == 0.4
    assert out["big_payoff"][0]["setup"] == "sr_rejection" and out["pips_by_symbol"]["US30"] == T["pips"]


# ── Nov 7 2026: Astra's review of the Analysis page ──────────────────────────
def _mini(tmp_path, rows):
    j = Journal(str(tmp_path / "m.sqlite"))
    for i, (sym, r, mfe) in enumerate(rows):
        j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple,mfe_r,exit_reason,bias_mode,realized) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (f"t{i}", sym, "LONG", "smc_mss:5m@x", "closed",
                     f"2026-11-0{i + 2}T10:00:00-05:00", f"2026-11-0{i + 2}T11:00:00-05:00", r, mfe, "stop", "aligned", r * 100))
    j.db.commit()
    return j


NOW = pd.Timestamp("2026-11-07 12:00", tz="America/New_York")


def test_payoff_in_r_across_instruments(tmp_path):
    # Astra's example: +1R, +1R gold and −1R NDQ → 1× in R whatever the pip sizes
    out = A.build(_mini(tmp_path, [("XAUUSD", 1.0, 1.0), ("XAUUSD", 1.0, 1.0), ("NDQ", -1.0, 0.2)]).db, 30, NOW)
    assert out["totals"]["payoff_r"] == 1.0 and out["totals"]["win_nz"] == round(2 / 3, 3)


def test_zero_r_trades_are_neither_side(tmp_path):
    out = A.build(_mini(tmp_path, [("NDQ", 2.0, 2.0), ("NDQ", 0.0, 0.5), ("NDQ", -1.0, 0.1)]).db, 30, NOW)["totals"]
    assert out["payoff_r"] == 2.0 and out["win_nz"] == 0.5 and out["flat_n"] == 1


def test_capture_uses_matched_records(tmp_path):
    # Astra's example: two +1R winners, one peak +2R recorded, one peak missing → 50%, coverage 1 of 2
    e = A.build(_mini(tmp_path, [("NDQ", 1.0, 2.0), ("NDQ", 1.0, None)]).db, 30, NOW)["excursion"]
    assert e["kept"] == 0.5 and e["kept_cov"] == [1, 2] and e["mfe_cov"] == [1, 2] and e["reached_1r"] == 1.0


def test_giveback_shares_have_their_denominators(tmp_path):
    out = A.build(_mini(tmp_path, [("NDQ", -1.0, 1.2), ("NDQ", 1.5, 1.6), ("NDQ", -1.0, 0.3), ("NDQ", -1.0, None)]).db, 30, NOW)
    assert out["giveback_share"] == round(1 / 3, 3)                       # of trades with a recorded peak
    assert out["excursion"]["gave_back_of_reached"] == 0.5 and out["excursion"]["reached_n"] == 2


def test_curve_starts_at_zero_and_keeps_the_true_high(tmp_path):
    j = Journal(str(tmp_path / "c.sqlite"))
    r = [1.0] * 400 + [-1.0] * 400 + [5.0] + [-1.0] * 300            # the +5 spike sits inside a thinned bucket
    for i, x in enumerate(r):
        ts = (pd.Timestamp("2026-11-01 00:00", tz="America/New_York") + pd.Timedelta(minutes=5 * i)).isoformat()
        j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple) VALUES(?,?,?,?,?,?,?,?)",
                     (f"c{i}", "NDQ", "LONG", "smc_mss:5m@x", "closed", ts, ts, x))
    j.db.commit()
    out = A.build(j.db, 30, NOW)
    cs, cv = out["curve_stats"], out["curve"]
    assert cv[0]["r"] == 0 and cv[0]["i"] == 0 and cs["n"] == len(r) and cs["high"] == 400.0 and cs["last"] == sum(r)
    assert max(p["r"] for p in cv) == cs["high"] and min(p["r"] for p in cv) == cs["low"]
    assert any(p["r"] == 5.0 for p in cv)                              # the spike's peak survives thinning
    assert len(cv) <= 1201 and [p["i"] for p in cv] == sorted(p["i"] for p in cv)


def test_signal_scope_reports_unapplied_filters(tmp_path):
    j = _journal(tmp_path)
    out = A.build(j.db, 30, pd.Timestamp("2026-11-04 12:00", tz="America/New_York"), filters={"bias": "aligned"})
    assert out["signal_scope"]["unapplied"] == ["bias"] and out["signals"]["seen"] == 4 and out["totals"]["n"] == 2
    assert A.build(j.db, 30, NOW, filters={"symbol": "US30"})["signal_scope"]["unapplied"] == []


def test_one_trade_endpoint(tmp_path):
    ctx = make_ctx(tmp_path)
    c = TestClient(build_app(ctx))
    rows = c.get("/api/trades").json()
    assert rows
    one = c.get(f"/api/trades/{rows[0]['id']}").json()
    assert one["id"] == rows[0]["id"] and isinstance(one["events"], list) and "pips" in one
    assert c.get("/api/trades/nope").status_code == 404
