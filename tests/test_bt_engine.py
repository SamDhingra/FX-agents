"""Backtest engine: fills, exits, costs, controls, the look-ahead audit, the CLI, and trade-by-trade parity with the
two modules that ran this week's specs (vol_breakout, h4_donchian)."""
import json

import numpy as np
import pandas as pd
import pytest

from fxagents.bt import Costs, Exits, Signal, Strategy, data, engine, stats
from fxagents.bt.data import MIN
from fxagents.bt.run import load_plugin, main

RAW = Costs(stop_slip_frac=0, cad=False, financing_bps=0, rollover_shield=None, same_bar_check=False)


def mk(bars, sp=0.2, start="2025-03-04 14:00"):
    """Minute frame from mid (o, h, l, c) tuples; 14:00 UTC = 09:00 NY."""
    idx = pd.date_range(start, periods=len(bars), freq="1min", tz="UTC")
    a = np.array(bars, float)
    d = pd.DataFrame(index=idx)
    for i, f in enumerate("ohlc"):
        d[f"bid_{f}"], d[f"ask_{f}"] = a[:, i] - sp / 2, a[:, i] + sp / 2
    return data.from_frame(d)


def flat(n, p=100.0):
    return [(p, p + 0.05, p - 0.05, p)] * n


class One(Strategy):
    news_block = None
    costs = RAW

    def __init__(self, sig, **kw):
        super().__init__(**kw)
        self.sig = sig

    def signals(self, m):
        return [self.sig(m)] if callable(self.sig) else list(self.sig)


def run(m, sig, exits=Exits(), costs=RAW, controls=False):
    s = One(sig)
    s.exits, s.costs = exits, costs
    return engine.simulate(s, m, controls=controls)


def test_market_long_fills_on_the_ask_and_stops_on_the_bid():
    m = mk(flat(5) + [(100, 100, 98, 98)] + flat(5, 98))
    r = run(m, lambda m: Signal(t=int(m.ns[2]), side=1, stop=99.0))
    t = r["trades"][0]
    assert t["entry"] == pytest.approx(100.1) and t["exit_reason"] == "stop"
    assert t["R"] == pytest.approx(-1.0) and t["R_2x"] == pytest.approx(-1 - 0.2 / 1.1)


def test_target_partials_and_the_same_bar_check():
    up = [(100, 101.5, 99.95, 101.4)]
    m = mk(flat(3) + up + [(101.4, 101.5, 99.0, 99.0)] + flat(3, 99))
    ex = Exits(target_r=3.0, partials=[(1.0, 0.5, 0.5)])
    sig = lambda m: Signal(t=int(m.ns[1]), side=1, stop=99.1)            # ask entry 100.1 → R = 1.0
    t = run(m, sig, ex)["trades"][0]
    assert t["exit_reason"] == "partial_stop"
    assert t["events"][0]["kind"] == "partial"
    assert t["R"] == pytest.approx(0.5 * 1.0 + 0.5 * 0.5)                # half at +1R, half at the +0.5R stop
    # same-bar check: the partial's minute itself trades back through the new stop
    m2 = mk(flat(3) + [(100, 101.5, 100.3, 100.4)] + flat(3, 100.4))
    a = run(m2, sig, ex, costs=Costs(**{**RAW.__dict__, "same_bar_check": True}))["trades"][0]
    b = run(m2, sig, ex)["trades"][0]
    assert a["exit_reason"] == "stop_same_bar" and b["exit_reason"] != "stop_same_bar"


def test_limit_entry_needs_the_ask_to_trade_through():
    m = mk(flat(3) + [(100, 100, 99.75, 99.8)] + [(99.8, 99.8, 99.35, 99.6)] + flat(5, 99.6))
    sig = lambda m: Signal(t=int(m.ns[1]), side=1, stop=98.0, entry="limit", price=99.5, expire_min=30)
    t = run(m, sig)["trades"][0]
    assert t["entry_time"] == m.idx[4] and t["entry"] == pytest.approx(99.5)   # ask low 99.85 at [3] isn't enough
    none = run(m, lambda m: Signal(t=int(m.ns[1]), side=1, stop=98, entry="limit", price=99.3, expire_min=30))
    assert not none["trades"]


def test_shorts_mirror_longs():
    m = mk(flat(3) + [(100, 101.2, 100, 101.2)] + flat(3, 101.2))
    mm = mk([(200 - o, 200 - l, 200 - h, 200 - c) for o, h, l, c in (flat(3) + [(100, 101.2, 100, 101.2)] + flat(3, 101.2))])
    ex = Exits(target_r=1.0)
    lo = run(m, lambda m: Signal(t=int(m.ns[1]), side=1, stop=99.1), ex)["trades"][0]
    sh = run(mm, lambda m: Signal(t=int(m.ns[1]), side=-1, stop=100.9), ex)["trades"][0]
    assert lo["R"] == pytest.approx(sh["R"]) and lo["exit_reason"] == sh["exit_reason"] == "target"


def test_cad_conversion_and_coin_control():
    m = mk(flat(3) + [(100, 101.2, 100, 101.2)] + flat(30, 101.2) + [(101.2, 101.2, 97, 97)] + flat(5, 97))
    sig = lambda m: Signal(t=int(m.ns[1]), side=1, stop=99.1)
    r = run(m, sig, Exits(target_r=1.0), costs=Costs(**{**RAW.__dict__, "cad": True}), controls=True)
    assert r["trades"][0]["R"] == pytest.approx(0.99)
    assert len(r["coin"]) == 1 and r["coin"][0]["side"] == 0


def test_flat_time_and_news_block():
    m = mk(flat(400))                                                     # 09:00 → 15:40 NY
    t = run(m, lambda m: Signal(t=int(m.ns[1]), side=1, stop=95), Exits(flat_at=600))["trades"][0]
    assert t["exit_reason"] == "flat" and t["exit_time"].tz_convert("America/New_York").hour == 10


class Peeker(Strategy):
    """Cheats: decides at minute i using the close 30 minutes later."""
    news_block = None

    def signals(self, m):
        return [Signal(t=int(m.ns[i]) + MIN, side=1, stop=float(m.c[i]) - 1) for i in range(0, len(m) - 30, 97)
                if m.c[i + 30] > m.c[i]]


class Honest(Strategy):
    news_block = None

    def signals(self, m):
        return [Signal(t=int(m.ns[i]) + MIN, side=1, stop=float(m.c[i]) - 1) for i in range(1, len(m))
                if (m.ns[i] + MIN) % (97 * MIN) == 0 and m.c[i] > m.c[i - 1]]


def test_lookahead_audit_catches_a_peek():
    from tests.test_gemini_smc import frame, walk
    m = data.from_frame(frame(walk(seed=3, n_days=20)))
    s, h = Peeker(), Honest()
    a = engine.lookahead_audit(s, m, s.signals(m), 10, warm_days=2)
    b = engine.lookahead_audit(h, m, h.signals(m), 10, warm_days=2)
    assert a["checked"] == 10 and a["failed"] > 0
    assert b["checked"] > 0 and b["failed"] == 0


def test_parity_with_vol_breakout_module():
    import fxagents.vol_breakout as V
    from fxagents.gemini_smc import block_mask
    from tests.test_gemini_smc import frame, walk
    df = frame(walk(seed=31, n_days=120))
    a = V.prepare(df)
    T = pd.DataFrame(V.execute(a, V.find_trades(a, True), block_mask(a, 15, 15), np.random.default_rng(1))[0])
    cls, _ = load_plugin("btplugins/vol_breakout_v1.py")
    s = cls()
    s.costs = RAW
    N = pd.DataFrame(engine.simulate(s, data.from_frame(df), controls=False)["trades"])
    assert len(T) == len(N) > 20
    assert (T.entry_time.values == N.entry_time.values).all() and (T.exit_time.values == N.exit_time.values).all()
    assert np.allclose(T.R, N.R, atol=1e-9) and np.allclose(T.R_2x, N.R_2x, atol=1e-9)


def test_parity_with_h4_donchian_module():
    import fxagents.h4_donchian as H
    from fxagents.gemini_smc import block_mask
    from tests.test_h4_donchian import gold
    # EST only (Nov 7 2022 → Mar 9 2023): the old module's 4H grid drifts an hour under daylight time (its bars then
    # close at 02/06/10/14 NY, so it never entered from March to November) — the engine's grid is the NY wall clock
    df = gold(122, 4, start="2022-11-07 18:00")
    a = H.prepare(df)
    T = pd.DataFrame(H.execute(a, H.find_trades(a, False), block_mask(a, 15, 15), np.random.default_rng(1))[0])
    cls, _ = load_plugin("btplugins/h4_donchian_trend_v1.py")
    s = cls(use_bias=False)
    s.costs = Costs(stop_slip_frac=0, cad=False, same_bar_check=False)     # financing + rollover shield ON, as theirs
    N = pd.DataFrame(engine.simulate(s, data.from_frame(df), controls=False)["trades"])
    assert len(T) == len(N) >= 3
    assert (T.exit_time.values == N.exit_time.values).all()
    assert np.allclose(T.R, N.R, atol=1e-9) and np.allclose(T.R_2x, N.R_2x, atol=1e-9)


def test_stats_gates():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-02 15:00", periods=300, freq="1D", tz="UTC")
    tr = [{"entry_time": t, "exit_time": t, "side": 1, "R": float(rng.normal(0.3, 1)), "R_2x": 0.2, "cost_R": 0.1,
           "hold_min": 30.0, "overnight": False, "exit_reason": "target"} for t in idx]
    coin = [{**x, "R": -0.05} for x in tr]
    m = mk(flat(10), start="2024-01-02 15:00")
    m.idx = idx
    out = stats.summarize({"trades": tr, "coin": coin, "funnel": {}}, m)
    assert out["gates"]["≥ 100 trades"] and out["gates"]["beats the coin flip"]
    assert "PASS" in out["gates"] and len(out["by_year"]) == 1


def _seen_export(tmp_path, days=40):
    from tests.test_gemini_smc import frame, walk
    df = frame(walk(seed=31, n_days=days))
    exp = tmp_path / "data/export/holdout_m1"
    exp.mkdir(parents=True)
    out = df[[c for c in df.columns if c[:3] in ("bid", "ask")]].copy()
    out.insert(0, "time", out.index.strftime("%Y-%m-%dT%H:%M:%SZ"))
    out.to_csv(exp / "XAUUSD_M1.csv.gz", index=False)
    (tmp_path / "btplugins").mkdir()
    (tmp_path / "btplugins/vb.py").write_text(open("btplugins/vol_breakout_v1.py").read())
    return df


def test_cli_runs_through_the_ledger(tmp_path, monkeypatch, capsys):
    from fxagents.bt import ledger
    _seen_export(tmp_path)
    monkeypatch.chdir(tmp_path)
    main(["run", "btplugins/vb.py", "--data", "seen", "--audit", "3", "--out", "res"])
    txt = capsys.readouterr().out
    assert "vol_breakout_v1" in txt
    assert json.loads((tmp_path / "res/summary.json").read_text())["run"]["role"] == "seen"
    assert (tmp_path / "data/bt/cache/seen_XAUUSD/ns.npy").exists()
    (r,) = ledger.runs()
    assert r["status"] == "done" and r["source"] == "cli" and r["passed"] == 0
    with pytest.raises(SystemExit, match="vault refused"):
        main(["run", "btplugins/vb.py", "--data", "vault"])
    w = data.window("seen", "XAUUSD", int(data.load("seen", "XAUUSD").ns[100]), int(data.load("seen", "XAUUSD").ns[160]))
    assert len(w) == 60


def test_vault_opens_once_and_only_for_the_identical_passer(tmp_path, monkeypatch):
    from fxagents.bt import jobs, ledger
    _seen_export(tmp_path, 25)
    monkeypatch.chdir(tmp_path)
    cat = ledger.catalog()
    (p,) = cat["plugins"]
    assert p["name"] == "vol_breakout_v1" and p["params"]["box_bars"] == 12 and not p["vault"]["eligible"]
    with pytest.raises(ValueError, match="unknown parameter"):
        ledger.enqueue("vb.py", "seen", overrides={"nope": 1})
    rid = ledger.enqueue("vb.py", "seen")
    assert ledger.claim()["id"] == rid
    jobs.execute(rid, audit=0)
    ledger.update(rid, passed=1)                                         # pretend it passed every gate
    with pytest.raises(PermissionError):
        ledger.enqueue("vb.py", "vault", overrides={"box_bars": 10})     # different params → not the same strategy
    v = ledger.enqueue("vb.py", "vault")
    with pytest.raises(PermissionError, match="already opened"):
        ledger.enqueue("vb.py", "vault")
    assert ledger.get(v)["role"] == "vault"
    (tmp_path / "btplugins/vb.py").write_text((tmp_path / "btplugins/vb.py").read_text() + "\n# edit\n")
    with pytest.raises(PermissionError):
        ledger.enqueue("vb.py", "vault")                                 # changed code → must pass seen again
    assert ledger.catalog()["plugins"][0]["tries"] == {"seen": 1}


def test_dashboard_api_queue_worker_results_and_chart_bars(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from fxagents.bt import jobs
    from fxagents.dashboard.server import build_app
    from tests.test_dashboard_insights import make_ctx
    ctx = make_ctx(tmp_path)
    ctx.cfg["dashboard"]["token"] = "tok"
    _seen_export(tmp_path, 25)
    monkeypatch.chdir(tmp_path)
    c = TestClient(build_app(ctx))
    H = {"x-token": "tok"}
    cat = c.get("/api/bt", headers=H).json()
    assert cat["plugins"][0]["file"] == "vb.py" and {d["name"] for d in cat["datasets"]} >= {"seen", "vault"}
    assert c.post("/api/bt/run", json={"plugin": "vb.py", "dataset": "seen"}).status_code == 401
    bad = c.post("/api/bt/run", headers=H, json={"plugin": "vb.py", "dataset": "vault"})
    assert bad.status_code == 400 and "vault refused" in bad.json()["detail"]
    rid = c.post("/api/bt/run", headers=H, json={"plugin": "vb.py", "dataset": "seen", "params": {"use_bias": False}}).json()["id"]
    jobs.worker(once=True)
    g = c.get(f"/api/bt/run/{rid}", headers=H).json()
    assert g["run"]["status"] == "done" and "gates" in g["summary"] and json.loads(g["run"]["params"])["use_bias"] is False
    assert "class VolBreakoutV1" in c.get(f"/api/bt/run/{rid}/code", headers=H).text
    b = c.get("/api/bt/bars", headers=H, params={"run": rid, "t0": "2024-11-05T13:00:00Z", "t1": "2024-11-05T15:00:00Z"}).json()
    assert b["tf"] == 1 and len(b["bars"]) == 120 and len(b["bars"][0]) == 6
    b = c.get("/api/bt/bars", headers=H, params={"run": rid, "t0": "2024-11-05", "t1": "2024-11-12"}).json()
    assert b["tf"] == 15
    assert c.get("/api/bt/run/../../x", headers=H).status_code in (400, 404)
    rid2 = c.post("/api/bt/run", headers=H, json={"plugin": "vb.py", "dataset": "seen"}).json()["id"]
    c.post(f"/api/bt/run/{rid2}/cancel", headers=H)
    assert c.get(f"/api/bt/run/{rid2}", headers=H).json()["run"]["status"] == "cancelled"


def test_4h_candles_stay_on_the_new_york_grid_through_dst():
    from tests.test_h4_donchian import gold
    m = data.from_frame(gold(300, 4))
    for key, want in (("4h", {60, 300, 540, 780, 1020, 1260}), ("1d", {1020})):
        e = pd.to_datetime(m.bars(key).end, utc=True).dt.tz_convert("America/New_York")
        assert set(e.dt.hour * 60 + e.dt.minute) == want


def test_crypto_pays_financing_every_day_with_no_wednesday_triple():
    n = 6 * 1440                                                         # Tue 09:00 NY → Mon 09:00, 24/7
    for sym, want in (("BTCUSD", 6), ("XAUUSD", 8)):                     # Wed..Sun 17:00 crossings = 6; gold: Wed ×3
        m = mk(flat(n, 100.0), start="2025-03-04 14:00")
        m.symbol = sym
        t = run(m, lambda m: Signal(t=int(m.ns[1]), side=1, stop=90.0),
                Exits(max_hold_min=6 * 1440 - 10, hold_overnight=True), costs=Costs(**{**RAW.__dict__, "financing_bps": 1.0}))
        assert t["trades"][0]["rollovers"] == want, sym


def test_adx_tracks_trend_strength():
    from fxagents.bt import ind
    n = 120
    up = pd.DataFrame({"h": np.arange(n) + 1.0, "l": np.arange(n) - 1.0, "c": np.arange(n) + 0.5})
    rng = np.random.default_rng(1)
    x = 100 + rng.normal(0, 1, n)
    chop = pd.DataFrame({"h": x + 1, "l": x - 1, "c": x})
    assert ind.adx(up, 14)[-1] > 90 and ind.adx(chop, 14)[-1] < 40


def test_daily_rsi2_adx2_plugin_signal_exits():
    from tests.test_h4_donchian import gold
    cls, _ = load_plugin("btplugins/daily_rsi2_adx2.py")
    s = cls()
    m = data.from_frame(gold(400, 4))
    res = engine.simulate(s, m)
    T = pd.DataFrame(res["trades"])
    assert len(T) > 10 and (T.side == 1).all() and len(res["coin"]) == len(T)
    assert (T.exit_reason == "signal_exit").mean() > 0.8 and set(T.exit_reason) <= {"signal_exit", "stop", "end"}
    assert T.overnight.any() and (T.fin_R > 0).any()
    loc = pd.to_datetime(T.exit_time).dt.tz_convert("America/New_York")
    assert ((loc.dt.hour == 18) & (loc.dt.minute == 0)).mean() > 0.8        # out at the next daily open
    a = engine.lookahead_audit(s, m, s.signals(m), 5, warm_days=200)
    assert a["checked"] == 5 and a["failed"] == 0


def test_bot_setups_bridge_runs_the_bots_own_code_causally():
    from tests.test_gemini_smc import frame, walk
    cls, _ = load_plugin("btplugins/bot_setups.py")
    m = data.from_frame(frame(walk(seed=31, n_days=90)), symbol="BTCUSD")
    s = cls(setup="dtfx_close_fib")
    sig = s.signals(m)
    T = pd.DataFrame(engine.simulate(s, m, sig, controls=False)["trades"])
    assert len(T) > 5 and set(T.exit_reason) <= {"stop", "partial_stop", "step_stop", "adjust_stop", "stop_same_bar",
                                                 "flat", "max_hold", "data_gap", "end"}
    assert (T.hold_min <= 241).all()
    loc = pd.to_datetime(T.entry_time).dt.tz_convert("America/New_York")
    mins = loc.dt.hour * 60 + loc.dt.minute
    assert mins.map(lambda x: any(a <= x < b for a, b in [(120, 300), (510, 690), (810, 930), (1200, 1440)])).all()
    assert engine.lookahead_audit(s, m, sig, 4, warm_days=40)["failed"] == 0
    with pytest.raises(ValueError):
        cls(setup="smt_divergence").signals(m)
