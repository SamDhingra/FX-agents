"""Execution order inside a minute (Oct 22 2026, from the PS-1 execution review): targets can fill in the fill minute
of a fill at the open, a known opening price beyond the target / a partial fills those resting orders before an
intrabar stop, MFE / MAE include the exit, market orders pay the slippage allowance, the paired gates, the random-
timing twins' exits, and the stricter look-ahead audit. Every case runs long and mirrored short."""
import numpy as np
import pytest

from fxagents.bt import Costs, Exits, Signal, Strategy, engine, stats
from tests.test_bt_engine import RAW, flat, mk, run


def mirror(bars):
    return [(200 - o, 200 - l, 200 - h, 200 - c) for o, h, l, c in bars]


def both(bars, stop, ex, entry="market", price=None, costs=RAW):
    """The same path long and mirrored short (prices around 100 ↔ 200 − p); returns the two trades."""
    out = []
    for side in (1, -1):
        b = bars if side > 0 else mirror(bars)
        st = stop if side > 0 else 200 - stop
        pr = None if price is None else (price if side > 0 else 200 - price)
        sig = (lambda st_, pr_: lambda m: Signal(t=int(m.ns[2]), side=side, stop=st_, entry=entry, price=pr_,
                                                 expire_min=30))(st, pr)
        out.append(run(mk(b), sig, ex, costs=costs)["trades"][0])
    assert out[0]["exit_reason"] == out[1]["exit_reason"] and out[0]["R"] == pytest.approx(out[1]["R"])
    return out[0]


# entry: signal at minute 2 → filled at that minute's open on the ask 100.1; stop 99.1 → R = 1, target 101.1
def test_target_in_the_fill_minute():
    bars = flat(2) + [(100, 101.5, 99.6, 101.3), (101.3, 101.3, 98.5, 98.5)] + flat(3, 98.5)
    t = both(bars, 99.1, Exits(target_r=1.0))
    assert t["exit_reason"] == "target" and t["R"] == pytest.approx(1.0)      # was a −1R stop the next minute
    assert t["exit_time"] == t["entry_time"]


def test_both_barriers_in_the_fill_minute_is_still_a_stop():
    bars = flat(2) + [(100, 101.5, 98.9, 100)] + flat(3)
    assert both(bars, 99.1, Exits(target_r=1.0))["exit_reason"] == "stop"


def test_an_open_beyond_the_target_fills_before_the_intrabar_stop():
    bars = flat(2) + [(100, 100.3, 99.9, 100.2), (101.4, 101.4, 98.5, 98.5)] + flat(3, 98.5)
    t = both(bars, 99.1, Exits(target_r=1.0))
    assert t["exit_reason"] == "target" and t["R"] == pytest.approx(1.2)      # the bid's open 101.3


def test_an_open_beyond_a_partial_banks_it_first():
    bars = flat(2) + [(100, 100.3, 99.9, 100.2), (101.4, 101.4, 98.5, 98.5)] + flat(3, 98.5)
    t = both(bars, 99.1, Exits(target_r=3.0, partials=[(1.0, 0.5, 0.1)]))
    assert t["exit_reason"] == "partial_stop"
    assert t["R"] == pytest.approx(0.5 * 1.2 + 0.5 * 0.1)                       # half at the open, half at +0.1R


def test_a_limit_fill_inside_the_minute_keeps_the_cautious_rule():
    # ask low 99.4 fills the 99.5 limit inside minute 2, whose high may have come BEFORE the fill → not a target
    bars = flat(2) + [(100, 101.8, 99.3, 100.3), (100.3, 100.3, 97.5, 97.5)] + flat(3, 97.5)
    t = both(bars, 98.5, Exits(target_r=1.0), entry="limit", price=99.5)
    assert t["entry"] in (pytest.approx(99.5), pytest.approx(100.5)) and t["exit_reason"] == "stop"
    assert t["exit_time"] > t["entry_time"]


def test_excursions_include_the_exit():
    win = flat(2) + [(100, 100.3, 99.9, 100.2), (100.2, 101.5, 100.1, 101.4)] + flat(3, 101.4)
    t = both(win, 99.1, Exits(target_r=1.0))
    assert t["exit_reason"] == "target" and t["mfe_r"] >= t["R"] - 1e-9 >= 0.99
    lose = flat(2) + [(100, 100.05, 99.9, 99.95), (99.95, 99.95, 98.0, 98.0)] + flat(3, 98)
    t = both(lose, 99.1, Exits(target_r=1.0))
    assert t["exit_reason"] == "stop" and t["mae_r"] <= t["R"] + 1e-9


def test_market_orders_pay_the_slippage_allowance():
    c = Costs(**{**RAW.__dict__, "market_slip_frac": 0.1})
    t = both(flat(12), 99.1, Exits(max_hold_min=3), costs=c)
    assert t["exit_reason"] == "max_hold"
    assert t["R"] == pytest.approx((99.9 - 0.02 - 100.12) / (100.12 - 99.1))
    assert Costs().market_slip_frac == pytest.approx(0.10)


def test_paired_gates_need_the_range_above_zero():
    import pandas as pd
    idx = pd.date_range("2024-01-02 15:00", periods=300, freq="1D", tz="UTC")
    rng = np.random.default_rng(3)
    tr = [{"entry_time": t, "exit_time": t, "side": 1, "R": float(rng.normal(0.30, 1)), "R_2x": 0.2, "cost_R": 0.1,
           "hold_min": 30.0, "overnight": False, "exit_reason": "target"} for t in idx]
    m = mk(flat(10), start="2024-01-02 15:00")
    m.idx = idx
    close = [{**x, "R": x["R"] - 0.01} for x in tr]                  # real beats its twin by only +0.01R
    out = stats.summarize({"trades": tr, "coin": close, "funnel": {}}, m)
    assert out["coin_edge"]["avg_R"] == pytest.approx(0.01) and out["coin_edge"]["ci_lo"] > 0     # constant gap
    noisy = [{**x, "R": float(rng.normal(0.29, 1))} for x in tr]     # a twin as good on average, independent noise
    out = stats.summarize({"trades": tr, "coin": noisy, "funnel": {}}, m)
    assert not out["gates"]["beats the coin flip (95% above 0)"] and not out["gates"]["PASS"]


def test_random_twins_use_the_strategy_exits_not_the_real_hold(monkeypatch):
    from tests.test_gemini_smc import frame, walk
    from fxagents.bt import data
    m = data.from_frame(frame(walk(seed=5, n_days=30)))

    class Every(Strategy):
        news_block = None
        costs = RAW
        exits = Exits(target_r=2.0, max_hold_min=120)

        def signals(self, mm):
            return [Signal(t=int(mm.ns[i]), side=1, stop=float(mm.c[i]) - 2.0) for i in range(2000, len(mm) - 500, 1440)]

    seen = []
    orig = engine.manage

    def spy(*a, **k):
        seen.append(k.get("exit_ns"))
        return orig(*a, **k)

    monkeypatch.setattr(engine, "manage", spy)
    res = engine.simulate(Every(), m)
    assert res["rand"] and res["trades"]
    assert all(x is None for x in seen)                              # no forced exit at the real trade's hold


class Peeks(Strategy):
    """Same time and side on truncated data, but the stop uses the LAST close of whatever data it gets."""
    news_block = None

    def signals(self, m):
        return [Signal(t=int(m.ns[i]) + 60_000_000_000, side=1, stop=float(m.c[-1]) - 5.0)
                for i in range(1, len(m)) if (int(m.ns[i]) // 60_000_000_000) % 300 == 0]


def test_audit_catches_a_changed_stop():
    rising = [(100 + 0.01 * i, 100.05 + 0.01 * i, 99.95 + 0.01 * i, 100 + 0.01 * i) for i in range(3000)]
    m = mk(rising)
    s = Peeks()
    a = engine.lookahead_audit(s, m, s.signals(m), 5, warm_days=0.1)
    assert a["cuts"] >= 5 and a["failed"] >= 4
    assert any("stop changed" in x for x in a["examples"])
