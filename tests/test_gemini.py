"""Gemini's three gold rules on synthetic minutes: each fires on the day built for it, at the level the spec gives,
and the shared exit engine does what the docstring says."""
import numpy as np
import pandas as pd

import fxagents.gemini_test as G
from fxagents.simple_rules import NY

HALF = 0.15                                           # half spread → 0.30 spread


def minutes(dates, price_fn, vol_fn=lambda d, m: 1.0):
    rows, idx = [], []
    for d in dates:
        for m in range(0, 17 * 60):
            p = price_fn(d, m)
            idx.append(pd.Timestamp(d) + pd.Timedelta(minutes=m))
            rows.append((p, vol_fn(d, m)))
    ix = pd.DatetimeIndex(idx).tz_localize(NY).tz_convert("UTC")
    p = np.array([r[0] for r in rows])
    df = pd.DataFrame(index=ix)
    for f in "ohlc":
        df[f"bid_{f}"], df[f"ask_{f}"] = p - HALF, p + HALF
    df["bid_h"] += 0.05; df["ask_h"] += 0.05; df["bid_l"] -= 0.05; df["ask_l"] -= 0.05
    for f in "ohlc":
        df[f"m_{f}"] = (df[f"bid_{f}"] + df[f"ask_{f}"]) / 2
    df["volume"] = [r[1] for r in rows]
    return df


def weekdays(start, n):
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start, periods=n)]


def wave(d, m, base=3000.0, amp=3.0):
    return base + amp * np.sin(2 * np.pi * m / 60)


# ── exit engine ──
def test_manage_target_stop_and_trailing():
    days = weekdays("2025-02-03", 2)
    ramp = lambda d, m: 3000 + (m - 600) * 0.2 if m >= 600 and d == days[1] else 3000.0
    a = G.prep(minutes(days, ramp))
    s, e = a["days"][max(a["days"])]
    j = G.at(a, s, e, 600)
    jx, px, why = G.manage(a, j, 1, 3000.15, 2990.15, G.Exits(target_r=2.0), G.at(a, s, e, 950))
    assert why == "target" and abs(px - (3000.15 + 20)) < 0.25            # +2R on a 10-point risk
    jx, px, why = G.manage(a, j, -1, 2999.85, 3009.85, G.Exits(target_r=2.0), G.at(a, s, e, 950))
    assert why == "stop" and 3009.85 <= px < 3009.85 + 0.25          # gapped past: out at the open
    # chandelier trail after +1R: a run-up then a drop of more than 1.5 ATR exits on the trail, in profit
    def up_down(d, m):
        if d != days[1] or m < 600:
            return wave(d, m)
        return 3000 + min(m - 600, 120) * 0.25 - max(m - 720, 0) * 0.5
    a = G.prep(minutes(days, up_down))
    s, e = a["days"][max(a["days"])]
    j = G.at(a, s, e, 600)
    ex = G.Exits(target_r=10, trail_mode="chandelier", trail_trig=1.0, trail_k=1.5)
    jx, px, why = G.manage(a, j, 1, a["ask_o"][j], a["ask_o"][j] - 10, ex, G.at(a, s, e, 950))
    assert why == "stop" and px > a["ask_o"][j] + 10                          # trailed stop, locked > +1R


def test_time_stop_and_flatten():
    days = weekdays("2025-02-03", 2)
    a = G.prep(minutes(days, lambda d, m: 3000.0))
    s, e = a["days"][max(a["days"])]
    j = G.at(a, s, e, 600)
    _, _, why = G.manage(a, j, 1, 3000.15, 2990.15, G.Exits(target_r=3, time_after_min=150, time_min_r=0.25),
                         G.at(a, s, e, 950))
    assert why == "time_stop"
    jx, _, why = G.manage(a, j, 1, 3000.15, 2990.15, G.Exits(target_r=3), G.at(a, s, e, 950))
    assert why == "flat_1550" and a["mod"][jx] == 950


# ── #2 London-to-NY ──
def lny_frame(last_is):
    days = weekdays("2025-01-06", 30)                 # no FOMC inside except where a test puts one
    def px(d, m):
        if d != days[-1]:
            return wave(d, m)
        if m < 180:
            return 3000.0
        if m < 495:
            return 3000 + (m - 180) / 315 * 10        # clean London rally +10
        if m < 525:
            return 3010.0
        return 3010 + min(m - 525, 60) * 0.1          # NY extends
    vol = lambda d, m: 3.0 if d == days[-1] and 180 <= m < 495 else 1.0
    return days, minutes(days, px, vol)


def test_lny_buys_the_new_york_break_of_a_strong_london_move(monkeypatch):
    days, m1 = lny_frame("rule")
    monkeypatch.setattr(G, "FOMC_DAYS", frozenset())
    a = G.prep(m1)
    tr, ctl = G.run_lny(a, np.random.default_rng(0))
    last = [t for t in tr if str(t["entry_time"].tz_convert(NY).date()) == days[-1]]
    assert len(last) == 1 and last[0]["side"] == 1
    t = last[0]
    level = a["m_h"][G.at(a, *a["days"][max(a["days"])], 180):G.at(a, *a["days"][max(a["days"])], 525)].max() + 0.5
    assert abs(t["entry"] - level) < 1e-9 and t["entry_time"].tz_convert(NY).hour * 60 + t["entry_time"].tz_convert(NY).minute >= 525
    assert abs(t["atr"] - max(0.5 * 10.1, 0.0035 * 3010.0)) < 0.5           # stop distance from the spec's max()
    assert len(ctl) == len(tr)


def test_lny_skips_fomc_days(monkeypatch):
    days, m1 = lny_frame("rule")
    monkeypatch.setattr(G, "FOMC_DAYS", frozenset({days[-1]}))
    tr, _ = G.run_lny(G.prep(m1), np.random.default_rng(0))
    assert not [t for t in tr if str(t["entry_time"].tz_convert(NY).date()) == days[-1]]


# ── #1 post-release drift ──
def test_pmrd_trades_the_cpi_bar_breakout(monkeypatch):
    days = weekdays("2025-01-13", 30)
    cpi = days[-1]
    monkeypatch.setattr(G, "events", lambda: {cpi: [(510, "CPI")]})
    def px(d, m):
        if d != cpi or m < 510:
            return wave(d, m)
        if m < 525:
            return 3000 + (m - 510) / 14 * 10          # strong bullish release bar, closes at its high
        return 3010 + min(m - 525, 30) * 0.3
    vol = lambda d, m: 5.0 if d == cpi and 510 <= m < 525 else 1.0
    a = G.prep(minutes(days, px, vol))
    tr, _ = G.run_pmrd(a, np.random.default_rng(0))
    assert len(tr) == 1 and tr[0]["side"] == 1 and tr[0]["event"] == "CPI"
    t = tr[0]
    assert t["entry_time"].tz_convert(NY).hour == 8 and 45 <= t["entry_time"].tz_convert(NY).minute < 60
    nn, _ = G.run_pmrd(a, np.random.default_rng(0), control=True)
    assert all(str(x["entry_time"].tz_convert(NY).date()) != cpi for x in nn)   # control never trades event days


# ── #3 cross-asset open ──
def test_xeq_needs_the_equity_confirmation(monkeypatch):
    monkeypatch.setattr(G, "FOMC_DAYS", frozenset())
    days = weekdays("2025-01-06", 30)
    last = days[-1]
    def gold(d, m):
        if d != last or m < 570:
            return wave(d, m)
        if m < 600:
            return 3000 + (m - 570) / 29 * 6
        return 3006 + min(m - 600, 60) * 0.2
    def nas(d, m, up=True):
        if d == last and 570 <= m < 600:
            return 20000 * (1 + (0.005 if up else 0.0) * (m - 570) / 29)
        return 20000.0 + (100 if d == last and m >= 600 and up else 0)
    flat = lambda d, m: 45000.0
    vol = lambda d, m: 2.0 if d == last and 570 <= m < 600 else 1.0
    a = G.prep(minutes(days, gold))
    N = G.open_moves(G.prep(minutes(days, nas, vol)))
    U = G.open_moves(G.prep(minutes(days, flat)))
    tr, _ = G.run_xeq(a, N, U, np.random.default_rng(0))
    hit = [t for t in tr if str(t["entry_time"].tz_convert(NY).date()) == last]
    assert len(hit) == 1 and hit[0]["side"] == 1 and hit[0]["duration_spread"] >= 0.0015
    # the same day with NAS flat: no duration tailwind, no safe-haven move → no trade
    N2 = G.open_moves(G.prep(minutes(days, lambda d, m: nas(d, m, up=False), vol)))
    tr2, _ = G.run_xeq(a, N2, U, np.random.default_rng(0))
    assert not [t for t in tr2 if str(t["entry_time"].tz_convert(NY).date()) == last]
