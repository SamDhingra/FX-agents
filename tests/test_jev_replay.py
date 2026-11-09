"""Jev historical replay (registered Nov 9 2026): as-of packets, labels, benchmarks, the cached caller (fake client,
no network) and the judge."""
import json
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from fxagents import jev_replay as J
from tests.test_breakout import frame


def m1_walk(days=12, seed=3, start="2026-01-05 00:00"):
    rng = np.random.default_rng(seed)
    n = 1440 * days
    return frame(5000 + np.cumsum(rng.normal(0, 0.3, n)), start=start)


def bars(m1):
    return J.mid_bars(m1, "15min"), J.mid_bars(m1, "1h")


def test_decisions_are_as_of_and_anonymous():
    m1 = m1_walk()
    m15, h1 = bars(m1)
    ds = J.decisions("XAUUSD", m15, h1, pd.Timestamp("2026-01-07"), pd.Timestamp("2026-01-14"))
    assert ds and {d["hour"] for d in ds} <= set(J.HOURS)
    d = ds[10]
    t = d["t"]
    # the same decision with every later minute physically removed gives the identical packet and features
    cut = m1[m1.index < t]
    m15c, h1c = bars(cut)
    m15c, h1c = m15c[m15c.index <= t], h1c[h1c.index <= t]
    # grading needs 4 future bars; append them back from the full data only for the label, never the packet
    m15g = pd.concat([m15c, m15[(m15.index > t)].iloc[:4]])
    again = [x for x in J.decisions("XAUUSD", m15g, h1c, d["date"], d["date"]) if x["t"] == t][0]
    assert again["packet"] == d["packet"] and again["state"] == d["state"] and again["mom"] == d["mom"]
    s = json.dumps(d["packet"])
    assert "XAUUSD" not in s and "2026" not in s and "500" not in s.split('"m15"')[0]
    assert len(d["packet"]["m15"]) == 16 and len(d["packet"]["h1"]) == 4
    assert d["packet"]["m15"][-1][0] == 0 and d["packet"]["m15"][-1][4] == 0.0       # last close is the decision price


def test_label_t60():
    idx = pd.date_range("2026-01-05 03:00", periods=40, freq="15min", tz="UTC")
    c = np.full(40, 100.0)
    m15 = pd.DataFrame({"o": c, "h": c + 0.5, "l": c - 0.5, "c": c}, index=idx)
    hidx = pd.date_range("2026-01-04 15:00", periods=30, freq="1h", tz="UTC")
    h1 = pd.DataFrame({"o": 100.0, "h": 101.0, "l": 99.0, "c": 100.0}, index=hidx)   # A = 2
    t = pd.Timestamp("2026-01-05 05:00", tz=J.NY).tz_convert("UTC")                    # 10:00 UTC
    k = m15.index.get_loc(t)
    m15.iloc[k + 1:k + 5, 3] = [100.5, 99.9, 100.4, 101.0]                              # 3 of 4 above, last = P + A/2
    up = [x for x in J.decisions("NDQ", m15, h1, pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-05")) if x["t"] == t][0]
    assert up["y"] == "up"
    m15.iloc[k + 4, 3] = 100.99                                                          # just short of +A/2
    nn = [x for x in J.decisions("NDQ", m15, h1, pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-05")) if x["t"] == t][0]
    assert nn["y"] == "neither"
    m15.iloc[k + 1:k + 5, 3] = [99.5, 99.0, 100.2, 98.9]
    dn = [x for x in J.decisions("NDQ", m15, h1, pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-05")) if x["t"] == t][0]
    assert dn["y"] == "down"


def test_mirror_compose_brier():
    p = {"m15": [[15, 0.1, 0.4, -0.2, 0.3]], "h1": [[0, -1, 1, -2, 0.5]], "asset": "a liquid CFD"}
    m = J.mirror(p)
    assert m["m15"] == [[15, -0.1, 0.2, -0.4, -0.3]] and m["h1"] == [[0, 1, 2, -1, -0.5]]
    assert J.mirror(m) == p
    v = J.compose(0.6, 0.25)
    assert v == pytest.approx([0.15, 0.45, 0.4]) and v.sum() == pytest.approx(1)
    assert J.brier([1, 0, 0], "up") == 0 and J.brier([0, 0, 1], "up") == 2
    assert J.brier([1 / 3] * 3, "neither") == pytest.approx(2 / 3)


def lab_frame(n_days=400, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for d in pd.bdate_range("2025-01-01", periods=n_days):
        for h in (3, 9):
            mom = int(rng.choice([-1, 1]))
            y = ("up" if mom > 0 else "down") if rng.random() < 0.5 else rng.choice(list(J.K))
            rows.append({"sym": "NDQ", "t": (d + pd.Timedelta(hours=h)).tz_localize("UTC"), "date": d, "hour": h,
                         "state": "mixed", "mom": mom, "y": y})
    return pd.DataFrame(rows)


def test_benchmarks_only_use_prior_sessions():
    lab = lab_frame(300)
    d = lab.date.iloc[-1]
    bm = J.benchmarks(lab, [d])
    # changing the outcome on the evaluated day itself must not change its forecast
    lab2 = lab.copy()
    lab2.loc[lab2.date == d, "y"] = "neither"
    bm2 = J.benchmarks(lab2, [d])
    for c in ("b_hour", "b_mom", "b_meas"):
        assert all(np.allclose(a, b) for a, b in zip(bm[c], bm2[c]))
    assert (bm.n_hist <= 252).all()
    # momentum is informative here, so the momentum benchmark leans to the previous hour's side
    r = bm.iloc[0]
    row = lab[(lab.date == d) & (lab.t == r.t)].iloc[0]
    assert (r.b_mom[0] > r.b_mom[1]) == (row.mom > 0)


class FakeClient:
    def __init__(self, fail_every=0):
        self.n, self.fail_every = 0, fail_every

    async def system_one(self, state, questions):
        self.n += 1
        assert "XAUUSD" not in json.dumps(state)
        if self.fail_every and self.n % self.fail_every == 0:
            return NS(answers={"event": NS(type="noul", noul=0.5)}, model="fake")          # unreadable: one missing
        last = state["m15"][-1][4] - state["m15"][-5][4]
        return NS(answers={"event": NS(type="noul", noul=0.4), "up_if_event": NS(type="noul", noul=0.7 if last <= 0 else 0.3)},
                  model="fake-1")


def test_cache_and_resume(tmp_path):
    todo = [(f"k{i}", {"m15": [[0, 0, 0, 0, 0]] * 5}) for i in range(7)]
    c = FakeClient(fail_every=3)
    n = J.asyncio.run(J.ask_all(todo, tmp_path / "a.jsonl", {}, 2, c))
    assert n == 7
    cache = J.load_cache(tmp_path / "a.jsonl")
    assert len(cache) == 7 and sum(not r["ok"] for r in cache.values()) == 2
    assert all(r["error"].startswith("unreadable") for r in cache.values() if not r["ok"])
    ok = next(r for r in cache.values() if r["ok"])
    assert ok["e"] == 0.4 and ok["model"] == "fake-1"


def test_run_end_to_end_with_fake_client(tmp_path):
    m1 = pd.concat([m1_walk(days=30, start="2025-12-01 00:00", seed=5)])
    m15, h1 = bars(m1)
    lab = pd.DataFrame(J.decisions("US30", m15, h1, pd.Timestamp("2025-12-03"), pd.Timestamp("2025-12-30")))
    lab2 = lab.copy()                              # shift a copy into the evaluation window so the run has 2026 decisions
    shift = pd.Timedelta(days=35)
    lab2["t"] = lab2.t + shift
    lab2["date"] = lab2.date + shift
    lab2 = lab2[lab2.date.dt.dayofweek < 5]
    full = pd.concat([lab, lab2], ignore_index=True)
    dry = J.run(dry_run=True, out=tmp_path, cfg={}, client=FakeClient(), lab=full)
    assert dry["dry_run"] and dry["todo"] == 2 * dry["decisions"] > 0
    assert (tmp_path / "sample_packet.json").exists()
    part = J.run(max_calls=5, out=tmp_path, cfg={}, client=FakeClient(), lab=full)
    assert part["complete"] is False
    res = J.run(out=tmp_path, cfg={}, client=FakeClient(), lab=full)
    assert res["complete"] and res["coverage"] == 1.0 and res["models"] == ["fake-1"]
    assert set(res["gates"]) == {"Jev answered ≥ 90%", "95% range above 0", "both halves > 0", "beats momentum-only"}
    assert res["mirror"]["n"] == res["n"]
    md = (tmp_path / "report.md").read_text()
    assert "measured + Jev" in md and ("PASS" in md or "FAIL" in md)
    # a fourth run asks nothing more
    assert J.run(out=tmp_path, cfg={}, client=FakeClient(), lab=full)["n"] == res["n"]


def test_judge_rewards_a_good_forecaster():
    rng = np.random.default_rng(0)
    rows = []
    for d in pd.bdate_range(J.START, J.END):
        for _ in range(3):
            y = rng.choice(list(J.K))
            base = np.array([1 / 3] * 3)
            good = np.array([0.8 if k == y else 0.1 for k in J.K])
            rows.append({"sym": "NDQ", "date": d, "y": y, "mom": 1, "b_hour": base, "b_mom": base, "b_meas": base,
                         "jev": good, "jev_m": good[[1, 0, 2]], "model": "m"})
    r = J.judge(pd.DataFrame(rows))
    assert r["pass"] and r["lo"] > 0 and r["mirror"]["mean_abs_gap"] < 1e-9
    for row in rows:
        row["jev"] = np.array([1 / 3] * 3)
    assert not J.judge(pd.DataFrame(rows))["pass"]
