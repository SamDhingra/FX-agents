"""m15_wait1 (registered Nov 2 2026): one-candle wait, judged once on 2016–2020."""
import numpy as np
import pandas as pd
import pytest

from fxagents import m15_timing as T
from fxagents import m15_wait as MW
from tests.test_m15_timing import cfg, market, recorded  # noqa: F401  (fixture)


def test_wait_one_candle_enters_at_the_next_m15_close_or_cancels(cfg):  # noqa: F811
    m1, _ = market(start="2021-03-01 00:00", days=12)
    A = T.Arrays(cfg, m1, "5min")
    from fxagents.research import full_exit, mgmt_profiles
    m = mgmt_profiles(cfg, "5min")["std"]
    hits = 0
    for i in range(300, 1500, 37):
        loc = A.locate(A.close_ts[i])
        if loc is None:
            continue
        j0 = loc[1]
        for side in (1, -1):
            tr = T.Trade(i, j0, side, A.C[j0] - side * 3.0, m, full_exit(cfg, "std"), 240.0)
            r, k, why = T.late_entry(A, tr, A.hs, forced_k=1)
            assert why in {"entered", "stop_first", "session", "stop_side", "no_fill", "no_data", "stop_too_wide"}
            if why == "entered":
                assert k == 1
                hits += 1
            else:
                assert r == 0.0
    assert hits > 0


def test_run_once_vault_judged_seen_shown(cfg, monkeypatch, tmp_path):  # noqa: F811
    m1, h1 = market(start="2021-03-01 00:00", days=40)
    rows = recorded(cfg, monkeypatch, m1, h1, n=400)
    src = tmp_path / "src"; src.mkdir()
    hist = tmp_path / "hist"; hist.mkdir()
    pd.to_pickle((m1, h1), hist / "XAUUSD.pkl")
    x = rows.assign(ts=rows.ts.astype(str), exit_ts=rows.exit_ts.astype(str))
    x.to_csv(src / "trades_seen_x_5m.csv.gz", index=False)
    x.to_csv(src / "trades_old_x_5m.csv.gz", index=False)
    import fxagents.whatif_judge as J
    monkeypatch.setitem(J.PERIODS, "vault", (pd.Timestamp("2021-01-01", tz="America/New_York"),
                                             pd.Timestamp("2022-01-01", tz="America/New_York"), None))
    srcs = {"vault": (src, hist, "trades_old_"), "seen": (src, hist, "trades_seen_")}
    res = MW.run(tmp_path / "out", cfg=cfg, src=srcs)
    assert res["vault"]["match"] > 0.98 and res["seen"]["pass"] is False
    assert res["vault"]["flagged"] > 0 and res["vault"]["changed"] > 0
    rep = (tmp_path / "out/report.md").read_text()
    assert "2016–2020 (judged)" in rep and "2021–2026 (shown)" in rep
    with pytest.raises(SystemExit):
        MW.run(tmp_path / "out", cfg=cfg, src=srcs)
