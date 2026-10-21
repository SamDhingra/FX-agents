"""Oct 2026 audit, batch 2: the Selector's simulator pays the spread (F3); the journal is reconciled with OANDA (F9),
including how far target exits fill from their level (F5 evidence)."""
from __future__ import annotations

import asyncio
import copy
import json
import sqlite3

import numpy as np
import pandas as pd

from fxagents import reconcile as R
from fxagents.config import load_config
from fxagents.sim import Mgmt, backtest
from fxagents.strategies import BUILTIN

CFG = load_config("config.yaml")
CFG1 = copy.deepcopy(CFG)
CFG1["instruments"]["NDQ"]["multiplier"] = 1.0          # 1 unit = 1 USD a point, so the hand-made rows add up


# ── F3 ───────────────────────────────────────────────────────────────────
def _frame(n=3000, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-03-02 08:30", periods=n, freq="5min", tz="America/New_York")
    c = 20000 + np.cumsum(rng.normal(0, 8, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0, 6, n)
    l = np.minimum(o, c) - rng.uniform(0, 6, n)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1.0}, index=idx)


def test_f3_simulated_trades_pay_the_spread_in_r():
    from fxagents.strategies.base import Strategy
    df = _frame()
    ctx = Strategy.context(df)
    s = CFG["sessions"]
    m = Mgmt.from_cfg(CFG, rr=1.0, bar_minutes=5)
    got = None
    for cls in BUILTIN.values():
        st = cls(tf="5min")
        free = backtest(st, df, ctx, m, [["00:00", "23:59"]], s["flatten_at"])
        if len(free) >= 5:
            got = (st, free)
            break
    assert got, "no builtin strategy traded the synthetic frame"
    st, free = got
    paid = backtest(st, df, ctx, m, [["00:00", "23:59"]], s["flatten_at"], spread=2.0)
    assert len(paid) == len(free)
    for a, b in zip(free, paid):
        assert b["r_gross"] == a["r"] and b["cost_r"] > 0
        assert abs(b["r"] - (a["r"] - b["cost_r"])) < 1e-12
        assert abs(b["cost_r"] - 2.0 / abs(b["entry"] - b["stop"]) * (1 + b["adds"] * m.add_frac)) < 1e-12


def test_f3_strategist_charges_the_configured_spread():
    from fxagents.agents.trading import half_spread
    import fxagents.agents.strategist as S
    seen = {}
    real = S.backtest

    def spy(*a, **kw):
        seen["spread"] = kw.get("spread")
        return []
    S.backtest = spy
    try:
        ag = S.StrategistAgent.__new__(S.StrategistAgent)
        ag.cfg = CFG; ag.lc = {"is_frac": 0.67}
        df = _frame(300)
        st = next(iter(BUILTIN.values()))(tf="5min")
        ag.mgmt = lambda s: Mgmt.from_cfg(CFG, rr=1.0, bar_minutes=5)
        ag._bt(st, {"df": df, "bias": np.zeros(len(df)), "sym": "NDQ"}, "full")
    finally:
        S.backtest = real
    assert seen["spread"] == 2 * half_spread(CFG, "NDQ") and seen["spread"] > 0


# ── F9 / F5 ──────────────────────────────────────────────────────────────
def _journal(path, rows):
    con = sqlite3.connect(path)
    from fxagents.journal import SCHEMA
    con.executescript(SCHEMA)
    for r in rows:
        cols = ",".join(r)
        con.execute(f"INSERT INTO trades({cols}) VALUES({','.join('?' * len(r))})", list(r.values()))
    con.commit(); con.close()


def _row(pid, **kw):
    base = {"id": pid, "symbol": "NDQ", "side": "LONG", "strategy": "smc_ifvg:5m@v1", "status": "closed",
            "opened": "2026-10-15T10:00:00-04:00", "closed": "2026-10-15T11:00:00-04:00", "entry": 20000.0,
            "avg_entry": 20000.0, "exit_price": 20030.0, "initial_stop": 19980.0, "qty_initial": 1.0, "qty_gross": 1.0,
            "realized": 30.0, "r_multiple": 1.5, "exit_reason": "target", "events": "[]"}
    return base | kw


def _tr(pid, leg="initial0", state="CLOSED", price="20000.0", close="20030.0", pl="30.0", fin="-0.5", units="1",
        open_="2026-10-15T14:00:00Z", tid="101"):
    return {"id": tid, "instrument": "NAS100_USD", "price": price, "openTime": open_, "initialUnits": units,
            "currentUnits": "0" if state == "CLOSED" else units, "state": state, "averageClosePrice": close,
            "realizedPL": pl, "financing": fin, "clientExtensions": {"id": f"fxa-{pid}-{leg}" if pid else "manual"}}


def test_pos_id_parses_the_bots_client_extension():
    assert R.pos_id({"clientExtensions": {"id": "fxa-ab12cd34ef-initial0"}}) == "ab12cd34ef"
    assert R.pos_id({"clientExtensions": {"id": "fxa-ab12cd34ef-pyramid2"}}) == "ab12cd34ef"
    assert R.pos_id({"clientExtensions": {"id": "something"}}) is None and R.pos_id({}) is None


def test_reconcile_matches_flags_gaps_and_measures_differences(tmp_path):
    ev = json.dumps([{"kind": "partial", "price": 20019.0, "r": 1.0, "ts": "x"},                 # level 20020 → −0.05R
                     {"kind": "limit_exit", "price": 20041.0, "level": 20040.0, "ts": "y"}])    # +0.05R
    rows = [_row("aaaaaaaaaa", events=ev), _row("bbbbbbbbbb"), _row("cccccccccc", status="open", closed=None,
                                                                     exit_price=None, realized=0, r_multiple=None)]
    db = str(tmp_path / "j.sqlite")
    _journal(db, rows)
    closed = [_tr("aaaaaaaaaa", close="20031.0", pl="31.0", fin="0", tid="1"),       # OANDA exit 1 point better
              _tr("dddddddddd", tid="2"),                                            # journal never saw it
              _tr(None, tid="3", open_="2026-10-16T18:00:00Z")]                      # manual trade, no journal row
    open_ = [_tr("cccccccccc", state="OPEN", tid="4")]
    jr = R.load_journal(db, pd.Timestamp("2026-10-01", tz="UTC"))
    res = R.reconcile(CFG1, jr, closed, open_)
    s = R.summarize(res)
    assert s["matched"] == 1 and s["broker_only"] == 1 and s["untagged"] == 1 and s["state_mismatch"] == 0
    assert [x["id"] for x in res["journal_only"]] == ["bbbbbbbbbb"]
    p = res["pairs"][0]
    assert p["pl_diff_r"] == round(1.0 / 20.0, 3)                                    # risk_ccy = 30 / 1.5 = 20
    assert p["exit_diff_r"] == round(1.0 / 20.0, 3) and p["entry_diff_r"] == 0 and p["units_match"]
    slips = sorted(x["slip_r"] for x in res["target_fills"])
    assert slips == [-0.05, 0.05]
    md = R.report(res, s, 14)
    assert "Target fills" in md and "OANDA trades the journal doesn't have" in md and "20000" not in md.split("## Largest")[0]


def test_open_closed_disagreement_is_flagged(tmp_path):
    db = str(tmp_path / "j.sqlite")
    _journal(db, [_row("eeeeeeeeee")])                                                # journal: closed
    res = R.reconcile(CFG1, R.load_journal(db, pd.Timestamp("2026-10-01", tz="UTC")), [],
                      [_tr("eeeeeeeeee", state="OPEN")])                              # OANDA: still open
    assert res["state_mismatch"] == [{"id": "eeeeeeeeee", "symbol": "NDQ", "journal": "closed", "oanda": "OPEN"}]


def test_fetch_pages_back_until_the_window_starts():
    class C:
        def __init__(self):
            self.calls = []
        def acct(self, p): return "/v3/accounts/X" + p
        async def req(self, m, path, params=None, **kw):
            self.calls.append(dict(params))
            if "beforeID" not in params:
                return {"trades": [{"id": str(i), "openTime": "2026-10-20T10:00:00Z"} for i in (10, 9)]}
            return {"trades": [{"id": "8", "openTime": "2026-10-19T10:00:00Z"},
                               {"id": "7", "openTime": "2026-09-01T10:00:00Z"}]}
    c = C()
    got = asyncio.run(R.fetch_trades(c, pd.Timestamp("2026-10-01", tz="UTC"), page=2))
    assert [t["id"] for t in got] == ["10", "9", "8"] and c.calls[1]["beforeID"] == "9"


def test_untagged_trades_from_before_tagging_pair_by_instrument_and_open_time(tmp_path):
    db = str(tmp_path / "j.sqlite")
    _journal(db, [_row("ffffffffff", opened="2026-10-05T10:00:03-04:00")])
    jr = R.load_journal(db, pd.Timestamp("2026-10-01", tz="UTC"))
    res = R.reconcile(CFG1, jr, [_tr(None, open_="2026-10-05T14:00:05Z")], [])        # 2 s apart, no tag
    s = R.summarize(res)
    assert s["matched"] == 1 and s["matched_by_open_time"] == 1 and s["journal_only"] == 0 and s["untagged"] == 0
    res = R.reconcile(CFG1, jr, [_tr(None, open_="2026-10-05T14:10:00Z")], [])        # 10 minutes apart: no pair
    assert R.summarize(res)["matched"] == 0


def test_oanda_pl_is_converted_to_the_journals_usd_and_exit_uses_the_average(tmp_path):
    db = str(tmp_path / "j.sqlite")
    ev = "[]"
    # half closed at +1R (20020), rest at 20040: average exit 20030, realized 30 USD on 1 unit; last exit 20040
    _journal(db, [_row("gggggggggg", exit_price=20040.0, events=ev)])
    jr = R.load_journal(db, pd.Timestamp("2026-10-01", tz="UTC"))
    t = _tr("gggggggggg", close="20030.0", pl="41.1", fin="0")                         # 41.1 CAD = 30 USD at 0.73
    t["closeTime"] = "2026-10-15T15:00:00Z"
    res = R.reconcile(CFG1, jr, [t], [], fx=lambda ts: 30 / 41.1)
    p = res["pairs"][0]
    assert abs(p["pl_diff_r"]) < 1e-9 and abs(p["exit_diff_r"]) < 1e-9 and p["oanda_r"] == 1.5
