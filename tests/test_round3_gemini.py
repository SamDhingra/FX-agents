"""Round 3, Gemini's checks: their code unchanged, labels and availability handled outside (fxagents/round3_gemini)."""
import numpy as np
import pandas as pd

from fxagents import round3_gemini as G

NY = "America/New_York"


def m1_walk(days=30, seed=1, start="2025-02-03 00:00"):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=days * 1440, freq="min", tz=NY)
    idx = idx[idx.dayofweek < 5]
    c = 1000 + np.cumsum(rng.normal(0, 0.5, len(idx)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.2, "low": np.minimum(o, c) - 0.2, "close": c,
                         "spread": 0.3}, index=idx)


def test_labels_are_converted_so_the_stop_check_runs_its_15m_half():
    m1 = m1_walk()
    ts = pd.Timestamp("2025-02-20 10:00", tz=NY)
    sl = m1.loc[(m1.index >= ts - 5 * G.DAY) & (m1.index < ts)]
    fn = G._load("stop_inside_15m_noise")
    tiny = {"ts": ts, "side": 1, "tf": "3m", "risk_atr": 0.05}          # a stop far inside 15m noise
    ok, parts = G.available("stop_inside_15m_noise", tiny, sl)
    assert ok and parts["noise_part"] and fn(dict(tiny), sl)
    assert not fn({**tiny, "tf": "3min"}, sl) or parts["spread_part"]  # with the raw label the 15m half never runs


def test_short_history_is_unavailable_not_kept():
    m1 = m1_walk(days=1)
    ts = m1.index[100]
    for n in G.CHECKS:
        ok, _ = G.available(n, {"ts": ts, "side": 1, "tf": "5m", "risk_atr": 1.0}, m1.loc[m1.index < ts])
        assert not ok, n


def test_run_writes_report_with_stop_halves(tmp_path):
    rng = np.random.default_rng(4)
    m1 = m1_walk(days=60, seed=2, start="2021-03-01 00:00")
    hist = tmp_path / "hist"; hist.mkdir()
    pd.to_pickle((m1, None), hist / "XAUUSD.pkl")
    src = tmp_path / "src"; src.mkdir()
    ts = m1.index[rng.choice(np.arange(8 * 1440, len(m1) - 10), 300, replace=False)]
    pd.DataFrame({"sym": "XAUUSD", "tf": "3min", "ts": ts.astype(str), "side": rng.choice([1, -1], len(ts)),
                  "r": rng.normal(-0.05, 1, len(ts)), "risk_atr": rng.uniform(0.3, 2.0, len(ts)),
                  "day": ts.date.astype(str)}).to_csv(src / "trades_seen_x_3m.csv.gz", index=False)
    res = G.run("seen", src, hist, tmp_path / "out")
    assert set(res) == set(G.CHECKS)
    txt = (tmp_path / "out/report.md").read_text()
    assert "two halves separately" in txt and "chasing_exhausted_leg" in txt


def test_vault_judges_only_the_registered_spread_half(tmp_path, monkeypatch):
    import json
    rng = np.random.default_rng(6)
    m1 = m1_walk(days=60, seed=3, start="2017-03-01 00:00")
    m1["spread"] = rng.uniform(0.05, 1.5, len(m1))
    hist = tmp_path / "hist"; hist.mkdir()
    pd.to_pickle((m1, None), hist / "XAUUSD.pkl")
    src = tmp_path / "src"; src.mkdir()
    ts = m1.index[rng.choice(np.arange(8 * 1440, len(m1) - 10), 400, replace=False)]
    pd.DataFrame({"sym": "XAUUSD", "tf": "3min", "ts": ts.astype(str), "side": rng.choice([1, -1], len(ts)),
                  "r": rng.normal(-0.05, 1, len(ts)), "risk_atr": rng.uniform(0.5, 3.0, len(ts)),
                  "day": ts.date.astype(str)}).to_csv(src / "trades_old_x_3m.csv.gz", index=False)
    monkeypatch.chdir(tmp_path)
    seen = tmp_path / "data/year_test/round3_gemini_seen"; seen.mkdir(parents=True)
    (seen / "summary.json").write_text(json.dumps({"chasing_exhausted_leg": {"pass": False},
                                                   "info": {"stop_spread_part": {"pass": True}}}))
    res = G.run("vault", src, hist, tmp_path / "out")
    assert list(res) == ["stop_spread_part"]
    assert "Verdict:" in (tmp_path / "out/report.md").read_text()
