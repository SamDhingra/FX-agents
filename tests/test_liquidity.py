"""Higher-timeframe liquidity map (fxagents/liquidity.py): levels known only once confirmed, untaken until traded
through, and the two pre-registered checks (trap = swept on the trade's side in the last hour and back inside;
no room = the next level ahead is within 0.5 × ATR 1H)."""
import numpy as np
import pandas as pd
import pytest

from fxagents import liquidity as lq

TZ = "America/New_York"


def market(days=40, seed=3):
    idx = pd.date_range("2026-08-02 18:00", periods=days * 1440, freq="1min", tz=TZ)
    p = 40000 + np.cumsum(np.random.default_rng(seed).normal(0, 3, len(idx)))
    m1 = pd.DataFrame({"open": p, "high": p + 2, "low": p - 2, "close": p}, index=idx)
    h1 = m1.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return m1, h1


def test_levels_are_known_only_after_their_confirming_bars():
    m1, h1 = market()
    full = lq.level_map(h1)
    cut = h1.index[len(h1) // 2]
    part = lq.level_map(h1[h1.index < cut])
    known_full = full[full.known <= cut][["price", "side", "tf"]].round(6)
    known_part = part[part.known <= cut][["price", "side", "tf"]].round(6)
    key = lambda d: set(map(tuple, d.to_numpy()))          # noqa: E731
    assert key(known_full) == key(known_part)              # nothing known before the cut changes with later data
    got = full.groupby("tf").weight.first().to_dict()
    assert {"h1", "h4", "d", "pd", "pw", "asia", "london"} <= set(got)
    assert got.items() <= {"asia": 1, "d": 3, "h1": 1, "h4": 2, "london": 1, "pd": 3, "pw": 4, "w": 4}.items()


def _one_level(price, side, known, m1, h1):
    L = lq.Liquidity(m1, h1)
    L.set_levels(pd.DataFrame([{"price": price, "side": side, "tf": "h4", "weight": 2, "known": known}]))
    return L


def _spike(m1, at, to):
    m1 = m1.copy()
    m1.loc[at, "high"] = to
    return m1, m1.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def test_trap_after_a_buy_side_sweep():
    m1, h1 = market()
    t = m1.index[-600]
    known = t - pd.Timedelta(hours=3)
    lvl = float(m1[(m1.index >= known) & (m1.index < t)].high.max()) + 1      # untaken, and close to price
    m2, h2 = _spike(m1, t - pd.Timedelta(minutes=20), lvl + 5)
    L = _one_level(lvl, 1, known, m2, h2)
    long_ = L.at(t, 1)
    assert long_["trap"] and long_["swept"][0]["price"] == round(lvl, 2)
    assert not L.at(t, -1)["trap"]                        # a short isn't trapped by a buy-side sweep
    m3, h3 = _spike(m1, t - pd.Timedelta(minutes=90), lvl + 5)      # swept 90 min before → already taken, no trap
    assert not _one_level(lvl, 1, known, m3, h3).at(t, 1)["trap"]
    assert not _one_level(lvl, 1, known, m1, h1).at(t, 1)["trap"]   # never swept


def test_no_room_when_the_next_level_is_close():
    m1, h1 = market()
    t = m1.index[-600]
    known = t - pd.Timedelta(hours=3)
    hi_since = float(m1[(m1.index >= known) & (m1.index < t)].high.max())
    L = _one_level(hi_since + 0.5, 1, known, m1, h1)
    c = L.at(t, 1, price=hi_since + 0.4)
    assert c["room_atr"] is not None and c["room_atr"] < lq.ROOM_ATR and c["no_room"]
    far = _one_level(hi_since + 50 * c["atr_1h"], 1, known, m1, h1).at(t, 1, price=hi_since)
    assert not far["no_room"]


def test_judge_needs_kept_to_beat_removed():
    rng = np.random.default_rng(1)
    days = pd.date_range("2022-01-03", periods=600, freq="B")
    t = pd.DataFrame({"ts": np.repeat(days, 3), "day": np.repeat(days.astype(str), 3)})
    t["flag"] = rng.random(len(t)) < 0.2
    t["r"] = rng.normal(0.0, 1, len(t)) - 0.6 * t["flag"]
    assert lq.judge(t, "flag")["pass"]
    t["r"] = rng.normal(0.0, 1, len(t))
    j = lq.judge(t, "flag")
    assert not j["pass"] and j["diff_ci"][0] < 0 < j["diff_ci"][1]


def test_end_to_end_on_cell_files(tmp_path):
    m1, h1 = market(days=120, seed=9)
    hist, src = tmp_path / "hist", tmp_path / "src"
    hist.mkdir(); src.mkdir()
    pd.to_pickle((m1, h1), hist / "US30.pkl")
    rng = np.random.default_rng(2)
    ix = np.sort(rng.choice(np.arange(60 * 1440, len(m1) - 100), 400, replace=False))
    ts = m1.index[ix]
    t = pd.DataFrame({"sym": "US30", "ts": ts.astype(str), "day": ts.normalize().date.astype(str),
                      "side": rng.choice([1, -1], len(ix)), "r": rng.normal(0, 1, len(ix))})
    t.to_csv(src / "trades_seen_sr_rejection_15m_pb-x.csv.gz", index=False)
    res = lq.test(src, hist, tmp_path / "out")
    assert set(res) == {"trap", "no_room", "either"} and res["trap"]["n"] == 400
    md = (tmp_path / "out" / "report.md").read_text()
    assert "| trap |" in md and "sr_rejection_15m_pb-x" in md


def test_today_reads_journals_and_candles(tmp_path, monkeypatch):
    import asyncio
    import copy
    from fxagents import oanda
    from fxagents.journal import Journal
    from tests.test_core import CFG
    m1, h1 = market(days=60, seed=4)
    now = m1.index[-1] + pd.Timedelta(minutes=1)
    monkeypatch.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: now.tz_convert(tz) if tz else now))
    j = Journal(str(tmp_path / "j.sqlite"))
    opened = m1.index[-300]
    j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,entry,r_multiple) VALUES(?,?,?,?,?,?,?,?)",
                 ("a", "US30", "LONG", "sr_rejection:5m@v1", "closed", opened.isoformat(), float(m1.close.iloc[-301]), -1.0))
    j.db.commit()

    class Fake:
        async def req(self, method, path, params):
            src = h1 if params["granularity"] == "H1" else m1
            start = pd.Timestamp(params["from"])
            d = src[src.index > start].iloc[:5000]
            return {"candles": [{"time": ts.tz_convert("UTC").isoformat(), "complete": True,
                                 "mid": {"o": r.open, "h": r.high, "l": r.low, "c": r.close}} for ts, r in d.iterrows()]}
        async def aclose(self): pass
    monkeypatch.setattr(oanda, "oanda_from_cfg", lambda cfg: Fake())
    cfg = copy.deepcopy(CFG)
    cfg["storage"]["db_path"] = str(tmp_path / "j.sqlite")
    cfg["broker"] = "paper"
    cfg["instruments"]["US30"]["oanda_instrument"] = "US30_USD"
    md = asyncio.run(lq.today(cfg, 1, tmp_path / "out"))
    assert "| practice account |" in md and "US30" in md and "sr_rejection:5m" in md
