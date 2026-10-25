"""Oct 25 2026 engine review (ChatGPT's round-2 critique, checked and fixed):

1. the look-ahead audit catches a rule that uses the future to SKIP trades (both-way comparison, random cuts);
2. the news calendar covers the vault years 2016–2020 too;
3. a control that couldn't be computed fails its gate instead of dropping out;
4. "both halves" = halves of the period's calendar, not of the trade count;
5. "2×" charges every half-spread and all slippage again, not just the entry spread;
6. random-timing twins obey the rule's entry window, news blackout, spread cap and Friday flat;
7. financing counts every weekday rollover across a holiday gap;
8. one vault per strategy family per symbol;
9. candles carry n, the number of minutes they were built from."""
import numpy as np
import pandas as pd
import pytest

from fxagents.bt import Costs, Exits, Signal, Strategy, data, engine, ind, stats
from fxagents.bt.data import MIN
from fxagents.usd_calendar import SOURCES, events
from tests.test_bt_engine import RAW, flat, mk, run
from tests.test_h4_donchian import gold


def _gold(days=120, seed=3):
    df = gold(days, seed, sigma=0.4)
    num = [c for c in df.columns if c != "volume"]
    df[num] += 30000.0                                  # keep the random walk positive
    return data.from_frame(df)


class SkipCheat(Strategy):
    """Long every 15m close 10:00–15:00, but only when the close an hour later is higher (the future)."""
    name = "skip_cheat"
    exits = Exits(target_r=1.0, flat_at=960)
    news_block = None
    max_per_day = 3

    def signals(self, m):
        b = m.bars(15)
        c, a = b.c.to_numpy(), ind.atr(b, 14)
        mod = (b.index.hour * 60 + b.index.minute).to_numpy()
        out = []
        for i in range(20, len(b)):
            if not (600 <= mod[i] <= 900) or not np.isfinite(a[i]):
                continue
            if i + 4 < len(c) and c[i + 4] <= c[i]:     # look-ahead used to skip
                continue
            out.append(Signal(t=int(b.end.iloc[i]), side=1, stop=float(c[i] - a[i])))
        return out


class SameButHonest(SkipCheat):
    name = "honest"

    def signals(self, m):
        b = m.bars(15)
        c, a = b.c.to_numpy(), ind.atr(b, 14)
        mod = (b.index.hour * 60 + b.index.minute).to_numpy()
        return [Signal(t=int(b.end.iloc[i]), side=1, stop=float(c[i] - a[i])) for i in range(20, len(b))
                if 600 <= mod[i] <= 900 and np.isfinite(a[i]) and c[i] > c[i - 4]]


def test_audit_catches_a_rule_that_skips_trades_with_the_future():
    m = _gold()
    s = SkipCheat()
    a = engine.lookahead_audit(s, m, s.signals(m), 10, warm_days=20)
    assert a["failed"] > 0 and any("skipped by the full run" in x for x in a["examples"])
    h = SameButHonest()
    b = engine.lookahead_audit(h, m, h.signals(m), 10, warm_days=20)
    assert b["failed"] == 0 and b["checked"] > 20 and b["cuts"] >= 15


def test_audit_compares_expiry_and_per_signal_exits():
    a = Signal(t=1, side=1, stop=1.0)
    assert engine._same(a, Signal(t=1, side=1, stop=1.0, expire_min=30), 1.0) == "expire_min"
    assert engine._same(a, Signal(t=1, side=1, stop=1.0, exits={"target_r": 2.0}), 1.0) == "exits"
    assert engine._same(a, Signal(t=1, side=1, stop=1.001), 1.0) is None          # within 2% of the risk


@pytest.mark.parametrize("plugin", ["btplugins/ndq_fresh_cash_edge_v1.py", "btplugins/xau_h1_adr_exhaustion_v1.py",
                                    "btplugins/xau_h4_value_entry_v1.py", "btplugins/daily_rsi2_adx2.py"])
def test_honest_plugins_still_pass_the_stricter_audit(plugin):
    from fxagents.bt.run import load_plugin
    cls, _ = load_plugin(plugin)
    s = cls()
    df = gold(320, 7, sigma=0.4)
    num = [c for c in df.columns if c != "volume"]
    df[num] += 30000.0
    m = data.from_frame(df, symbol=s.symbol)
    a = engine.lookahead_audit(s, m, s.signals(m), 4, warm_days=s.warmup_days)
    assert a["failed"] == 0, a["examples"]


def test_news_calendar_covers_the_vault_years():
    for name, (dates, _) in SOURCES.items():
        years = {d[:4] for d in dates}
        assert {"2016", "2017", "2018", "2019", "2020"} <= years, name
        assert dates == sorted(dates) and len(set(dates)) == len(dates)
    ev = events()
    assert (510, "NFP") in ev["2016-01-08"] and (840, "FOMC") in ev["2019-12-11"]
    assert "2020-03-17" not in ev and "2020-03-18" not in ev                       # cancelled meeting


def _res(n=4, controls=True, rand=True):
    t0 = pd.Timestamp("2021-01-04 10:00", tz="UTC")
    tr = [{"entry_time": t0 + pd.Timedelta(days=30 * i), "exit_time": t0 + pd.Timedelta(days=30 * i, hours=1),
           "side": 1, "R": 1.0, "R_2x": 0.9, "cost_R": 0.05, "hold_min": 60, "overnight": False, "exit_reason": "target"}
          for i in range(n)]
    coin = [{**x, "R": 0.0, "R_2x": -0.1} for x in tr]
    rd = [{**x, "R": 0.0, "R_2x": -0.1, "edge": 1.0} for x in tr] if rand else []
    return {"trades": tr, "coin": coin, "rand": rd, "funnel": {}, "controls": controls}


def test_a_missing_timing_control_fails_its_gate():
    m = mk(flat(10))
    with_rand = stats.summarize(_res(), m)["gates"]
    no_rand = stats.summarize(_res(rand=False), m)["gates"]
    assert "beats random timing (95% above 0)" in no_rand and not no_rand["beats random timing (95% above 0)"]
    assert "beats random timing (95% above 0)" in with_rand
    off = stats.summarize(_res(rand=False, controls=False), m)["gates"]     # a variant run: no controls asked for
    assert "beats random timing (95% above 0)" not in off


def test_halves_split_at_the_calendar_midpoint():
    idx = pd.date_range("2021-01-01", "2021-12-31", freq="1D", tz="UTC")
    d = pd.DataFrame(index=idx)
    for f in "ohlc":
        d[f"bid_{f}"], d[f"ask_{f}"] = 100.0, 100.2
    m = data.from_frame(d)
    t0 = pd.Timestamp("2021-01-10", tz="UTC")
    tr = [{"entry_time": t0 + pd.Timedelta(days=i), "exit_time": t0 + pd.Timedelta(days=i), "side": 1,
           "R": -1.0 if i < 2 else 0.5, "R_2x": 0, "cost_R": 0, "hold_min": 1, "overnight": False, "exit_reason": "x"}
          for i in range(10)]                                   # all ten trades in January
    out = stats.summarize({"trades": tr, "coin": [], "rand": [], "funnel": {}, "controls": False}, m)
    assert out["halves_n"] == [10, 0] and np.isnan(out["halves"][1])
    assert not out["gates"]["positive in both halves"]          # an empty half can't be positive
    assert out["halves_split"] == "2021-07-01"


def test_2x_costs_charge_both_half_spreads_and_all_slippage():
    c = Costs(stop_slip_frac=0.15, market_slip_frac=0.10, cad=False, financing_bps=0, rollover_shield=None,
              same_bar_check=False)
    m = mk(flat(5) + [(100, 100, 98, 98)] + flat(5, 98))
    t = run(m, lambda m: Signal(t=int(m.ns[2]), side=1, stop=99.0), costs=c)["trades"][0]
    sp = 0.2
    R = 100.1 + 0.1 * sp - 99.0
    tc = sp * (0.5 + 0.10) + sp * (0.5 + 0.15)                  # entry half-spread + slip, stop half-spread + slip
    assert t["exit_reason"] == "stop"
    assert t["R_2x"] == pytest.approx(t["R"] - tc / R) and t["tc_R"] == pytest.approx(tc / R)


def test_rollovers_count_every_weekday_across_a_holiday_gap():
    day = lambda s: int(pd.Timestamp(s).value // (1440 * MIN))
    # Wednesday 16:59 → Wednesday 17:00: one Wednesday, charged 3×
    assert engine._rollovers(day("2025-03-05"), 1019, day("2025-03-05"), 1020, 2) == 3
    # Friday 16:59 → Sunday 18:00: Friday only (the weekend is booked on Wednesday)
    assert engine._rollovers(day("2025-03-07"), 1019, day("2025-03-09"), 1080, 2) == 1
    # Wednesday 16:59 → Monday 10:00 (Thursday + Friday closed): Wed 3 + Thu 1 + Fri 1
    assert engine._rollovers(day("2025-03-05"), 1019, day("2025-03-10"), 600, 2) == 5
    # … → Monday 18:00 also crosses Monday's 17:00
    assert engine._rollovers(day("2025-03-05"), 1019, day("2025-03-10"), 1080, 2) == 6
    # Sunday 23:59 → Monday 00:00 crosses no 17:00
    assert engine._rollovers(day("2025-03-09"), 1439, day("2025-03-10"), 0, 2) == 0
    # crypto (no triple day): every day, weekends included
    assert engine._rollovers(day("2025-03-07"), 1019, day("2025-03-09"), 1080, None) == 3


class _Fixed(Strategy):
    news_block = None
    exits = Exits(friday_flat_at=780, max_hold_min=120)
    costs = Costs(max_spread_frac=0.05)
    entry_windows = [(600, 700)]

    def signals(self, m):
        return []


def test_random_twins_obey_the_rules_entry_conditions():
    idx = pd.date_range("2025-03-03 13:00", periods=60 * 24 * 5, freq="1min", tz="UTC")       # Mon–Fri
    d = pd.DataFrame(index=idx)
    for f in "ohlc":
        d[f"bid_{f}"], d[f"ask_{f}"] = 100.0, 100.2
    m = data.from_frame(d)
    s, c = _Fixed(), _Fixed.costs
    k = int(np.flatnonzero((m.mod == 620) & (m.dow == 1))[0])                             # Tuesday 10:20 NY
    assert engine.twin_ok(m, k, 10.0, s.exits, s, c, None)
    assert not engine.twin_ok(m, k, 1.0, s.exits, s, c, None)                    # spread 0.2 > 5% of a 1.0 risk
    blk = np.zeros(len(m), bool); blk[k] = True
    assert not engine.twin_ok(m, k, 10.0, s.exits, s, c, blk)                     # news blackout
    k2 = int(np.flatnonzero((m.mod == 720) & (m.dow == 1))[0])
    assert not engine.twin_ok(m, k2, 10.0, s.exits, s, c, None)                   # outside the entry window
    s.entry_windows = None
    k3 = int(np.flatnonzero((m.mod == 800) & (m.dow == 4))[0])
    assert not engine.twin_ok(m, k3, 10.0, s.exits, s, c, None)                   # Friday after the Friday flat


def test_bars_count_their_minutes():
    m = mk(flat(130))
    b = m.bars(60)
    assert "n" in b.columns and int(b.n.max()) <= 60 and int(b.n.sum()) == 130


def test_one_vault_per_family(tmp_path, monkeypatch):
    from fxagents.bt import jobs, ledger
    from tests.test_bt_engine import _seen_export
    _seen_export(tmp_path, 25)
    src = (tmp_path / "btplugins/vb.py").read_text()
    (tmp_path / "btplugins/vb2.py").write_text(src.replace('name = "vol_breakout_v1"', 'name = "vol_breakout_v2"'))
    monkeypatch.chdir(tmp_path)
    assert ledger.family_of("vol_breakout_v2") == ledger.family_of("vol_breakout_v1") == "vol_breakout"
    assert ledger.family_of("x_v2", "c10") == "c10"
    for f in ("vb.py", "vb2.py"):
        rid = ledger.enqueue(f, "seen")
        assert ledger.claim()["id"] == rid
        jobs.execute(rid, audit=0)
        ledger.update(rid, passed=1)
    ledger.enqueue("vb.py", "vault")
    with pytest.raises(PermissionError, match="family already opened"):
        ledger.enqueue("vb2.py", "vault")
