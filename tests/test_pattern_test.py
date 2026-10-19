"""Chart patterns stage 2: signals are causal, mirror-symmetric, and trades follow the frozen geometry."""
import numpy as np
import pandas as pd

import fxagents.pattern_test as PT
from fxagents.gemini_smc import block_mask
from fxagents.gemini_test import prep
from tests.test_gemini_smc import frame, reflect, walk


def bars_of(seed=5, tf=15, days=70):
    mid = walk(n_days=days, seed=seed)
    m1 = frame(mid)
    return m1, PT.bars(m1, tf)


def key(s):
    return (s["family"], s["kind"], s["i"], s["side"], round(s["stop"], 6))


def test_signals_only_use_bars_up_to_the_trigger():
    _, b = bars_of()
    full = PT.signals(b)
    assert len(full) > 20 and {s["family"] for s in full} >= {"double", "flag"}
    for s in [x for x in full if x["i"] >= 40][:: max(1, len(full) // 25)]:
        part = PT.signals(b.iloc[: s["i"] + 1])                  # data ends at the trigger bar's close
        assert key(s) in {key(x) for x in part}, s


def test_stops_sit_on_the_losing_side_at_least_half_an_atr_away():
    _, b = bars_of(seed=9)
    c = b.close.to_numpy()
    for s in PT.signals(b):
        risk = s["side"] * (c[s["i"]] - s["stop"])
        assert risk >= PT.MIN_STOP * s["atr"] - 1e-9
        if s["target"] is not None:
            assert s["family"] in ("double", "hs")


def test_patterns_are_mirror_symmetric():
    mid = walk(seed=11)
    b, r = PT.bars(frame(mid), 15), PT.bars(frame(reflect(mid)), 15)
    flip = {"double_top": "double_bottom", "head_shoulders": "inverse_head_shoulders", "bull_flag": "bear_flag",
            "ascending_triangle": "descending_triangle", "rising_wedge": "falling_wedge", "channel_up": "channel_down"}
    flip |= {v: k for k, v in flip.items()} | {"symmetrical_triangle": "symmetrical_triangle"}
    A = {(s["kind"], s["i"], s["side"]) for s in PT.signals(b)}
    B = {(flip[s["kind"]], s["i"], -s["side"]) for s in PT.signals(r)}
    assert len(A) > 10 and len(A ^ B) <= 0.1 * len(A)          # ATR ties at the zigzag threshold can differ slightly


def test_trades_respect_the_frozen_exits():
    m1, b = bars_of(seed=3)
    a = prep(m1)
    tr, ctl = PT.execute(a, b, PT.signals(b), 15, block_mask(a, 15, 15), np.random.default_rng(1), "XAUUSD")
    assert len(tr) > 10 and len(ctl) >= len(tr) - 2
    T = pd.DataFrame(tr)
    assert set(T.exit_reason) <= {"stop", "target", "time_stop", "flat_1550", "closure", "end"}
    assert (T.hold_min <= PT.MAX_HOLD_BARS * 15 + 1).all()
    st = T[T.exit_reason == "stop"]
    assert (st.R <= -0.99).all()                                    # stops fixed: a stop-out is a full loss
    tg = T[T.exit_reason == "target"]
    assert (tg.R >= tg.target_r - 0.006).all()          # target_r is rounded in the row
    et = pd.to_datetime(T.entry_time).dt.tz_convert("America/New_York")
    mins = et.dt.hour * 60 + et.dt.minute
    assert not ((mins >= PT.NO_FILL[0]) & (mins < PT.NO_FILL[1])).any()
    for fam, x in T.groupby("family"):                              # one at a time per family
        x = x.sort_values("entry_time")
        assert (pd.to_datetime(x.entry_time).iloc[1:].values >= pd.to_datetime(x.exit_time).iloc[:-1].values).all()


def test_prereg_gold_1h_judges_only_the_holdout(tmp_path, monkeypatch):
    for ds in ("dev_m1", "holdout_m1"):
        d = tmp_path / "data/export" / ds
        d.mkdir(parents=True)
        m = frame(walk(n_days=60, seed=2 if ds == "dev_m1" else 8))
        m = m[[c for c in m.columns if not c.startswith("m_")]]
        m.index.name = "time"
        m.to_csv(d / "XAUUSD_M1.csv.gz")
    monkeypatch.chdir(tmp_path)
    PT.main_prereg("gold_1h", "dev_m1,holdout_m1", tmp_path / "out", 29)
    md = (tmp_path / "out/report.md").read_text()
    dev = next(l for l in md.splitlines() if l.startswith("| dev_m1"))
    hold = next(l for l in md.splitlines() if l.startswith("| holdout_m1"))
    assert "(in-sample)" in dev and "judged" in hold and ("PASS" in hold or "no pass" in hold)
    assert PT.PREREG["gold_1h"] == ("XAUUSD", 60)
