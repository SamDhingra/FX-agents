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
    df = gold(400, 4)
    a = H.prepare(df)
    T = pd.DataFrame(H.execute(a, H.find_trades(a, False), block_mask(a, 15, 15), np.random.default_rng(1))[0])
    cls, _ = load_plugin("btplugins/h4_donchian_trend_v1.py")
    s = cls(use_bias=False)
    s.costs = Costs(stop_slip_frac=0, cad=False, same_bar_check=False)     # financing + rollover shield ON, as theirs
    N = pd.DataFrame(engine.simulate(s, data.from_frame(df), controls=False)["trades"])
    assert len(T) == len(N) >= 5 and "trail_stop" in set(N.exit_reason)
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


def test_cli_runs_a_plugin_and_refuses_the_vault(tmp_path, monkeypatch, capsys):
    from tests.test_gemini_smc import frame, walk
    df = frame(walk(seed=31, n_days=40))
    exp = tmp_path / "data/export/holdout_m1"
    exp.mkdir(parents=True)
    out = df[[c for c in df.columns if c[:3] in ("bid", "ask")]].copy()
    out.insert(0, "time", out.index.strftime("%Y-%m-%dT%H:%M:%SZ"))
    out.to_csv(exp / "XAUUSD_M1.csv.gz", index=False)
    plug = tmp_path / "p.py"
    plug.write_text(open("btplugins/vol_breakout_v1.py").read())
    monkeypatch.chdir(tmp_path)
    main(["run", str(plug), "--data", "seen", "--audit", "3", "--out", "res"])
    txt = capsys.readouterr().out
    assert "vol_breakout_v1" in txt and "Look-ahead audit" in txt or "No trades" in txt
    assert json.loads((tmp_path / "res/summary.json").read_text())["funnel"]["signals"] >= 0
    assert (tmp_path / "data/bt/cache/seen_XAUUSD.npz").exists()
    with pytest.raises(SystemExit):
        main(["run", str(plug), "--data", "vault"])
