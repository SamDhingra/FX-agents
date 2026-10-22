"""Journal repair: stuck 'open' rows closed with OANDA's result, duplicates and lost paper trades voided, live
positions and today's rows never touched, dry run by default, backup before writing."""
import asyncio
import copy
import glob
import json
import sqlite3

import pandas as pd

from fxagents import journal_repair as JR
from fxagents.config import load_config
from fxagents.journal import SCHEMA

CFG = load_config("config.yaml")
NOW = pd.Timestamp("2026-10-22 10:00", tz="America/New_York")


def _db(path, rows):
    con = sqlite3.connect(path); con.executescript(SCHEMA)
    for r in rows:
        con.execute(f"INSERT INTO trades({','.join(r)}) VALUES({','.join('?' * len(r))})", list(r.values()))
    con.commit(); con.close()


def _row(i, **kw):
    return {"id": i, "symbol": "NDQ", "side": "LONG", "strategy": "smc_ifvg:5m@v1", "status": "open",
            "opened": "2026-10-05T10:00:00-04:00", "entry": 20000.0, "initial_stop": 19980.0, "qty_initial": 1.0,
            "qty_gross": 1.0, "events": "[]"} | kw


class Client:
    def __init__(self, trades): self.trades = trades
    def acct(self, p): return "/v3/accounts/X" + p
    async def req(self, m, path, params=None, **kw):
        if path.endswith("/summary"):
            return {"account": {"currency": "CAD"}}
        if "candles" in path:
            return {"candles": [{"time": "2026-10-01T21:00:00Z", "mid": {"c": "1.40"}}]}
        st = params["state"]
        if "beforeID" in (params or {}):
            return {"trades": []}
        return {"trades": [t for t in self.trades if t["state"] == st]}
    async def aclose(self): pass


def _t(cid, state="CLOSED", open_="2026-10-05T14:00:00Z", close="20040.0", pl="56.0"):
    return {"id": "1", "instrument": "NAS100_USD", "state": state, "openTime": open_, "closeTime": "2026-10-05T15:00:00Z",
            "initialUnits": "1", "averageClosePrice": close, "realizedPL": pl, "financing": "0",
            "clientExtensions": {"id": cid} if cid else {}}


def _cfg(tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["storage"]["db_path"] = str(tmp_path / "journal.sqlite")
    cfg["instruments"]["NDQ"]["multiplier"] = 1.0
    return cfg


def test_dry_run_plan_then_apply(tmp_path):
    cfg = _cfg(tmp_path)
    _db(cfg["storage"]["db_path"], [
        _row("aaaaaaaaaa"),                                                     # OANDA closed it (tag)
        _row("bbbbbbbbbb", opened="2026-10-06T10:00:00-04:00"),                 # still open at OANDA
        _row("cccccccccc", opened="2026-10-07T10:00:00-04:00"),                 # no OANDA trade at all
        _row("dddddddddd", opened="2026-10-22T09:45:00-04:00"),                 # today: never touched
        _row("eeeeeeeeee", opened="2026-10-08T10:55:06-04:00"),                 # duplicate of an orphan row
        _row("ffffffffff", strategy="orphan:unmanaged", status="closed", opened="2026-10-08T10:55:07-04:00",
             realized=-5.0, r_multiple=-0.25),
        _row("gggggggggg", opened="2026-10-09T10:00:00-04:00"),                 # held by the running app
    ])
    (tmp_path / "runtime_state.json").write_text(json.dumps({"positions": [{"id": "gggggggggg"}]}))
    _db(str(tmp_path / "journal_shadow.sqlite"), [_row("pppppppppp", strategy="playbook:NDQ")])
    _db(str(tmp_path / "journal_daily_rsi2_adx2.sqlite"), [_row("qqqqqqqqqq", strategy="daily")])
    trades = [_t("fxa-aaaaaaaaaa-initial0"), _t("fxa-bbbbbbbbbb-initial0", state="OPEN", open_="2026-10-06T14:00:00Z"),
              _t(None, open_="2026-10-08T14:55:07Z")]
    rep = asyncio.run(JR.run(cfg, False, client=Client(trades), now=NOW))
    plan = {p["id"]: p for p in rep["books"]["live"]["plan"]}
    assert set(plan) == {"aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc", "eeeeeeeeee", "ffffffffff"}
    assert plan["aaaaaaaaaa"]["action"] == "close" and plan["aaaaaaaaaa"]["realized"] == 40.0     # 56 CAD / 1.40
    assert plan["aaaaaaaaaa"]["r_multiple"] == 2.0 and plan["aaaaaaaaaa"]["exit_price"] == 20040.0
    assert plan["bbbbbbbbbb"]["action"] == "keep"
    assert plan["cccccccccc"]["action"] == "void"
    assert plan["eeeeeeeeee"]["action"] == "close" and "merged" in plan["eeeeeeeeee"]["why"]   # original + its orphan
    assert plan["ffffffffff"]["action"] == "void"
    assert [p["id"] for p in rep["books"]["shadow"]["plan"]] == ["pppppppppp"]
    assert "daily_rsi2_adx2" not in rep["books"]
    con = sqlite3.connect(cfg["storage"]["db_path"])
    assert con.execute("SELECT COUNT(*) FROM trades WHERE status='open'").fetchone()[0] == 6     # dry run: untouched
    con.close()
    rep = asyncio.run(JR.run(cfg, True, client=Client(trades), now=NOW))
    con = sqlite3.connect(cfg["storage"]["db_path"])
    st = dict(con.execute("SELECT id, status FROM trades").fetchall())
    con.close()
    assert st == {"aaaaaaaaaa": "closed", "bbbbbbbbbb": "open", "cccccccccc": "void", "dddddddddd": "open",
                  "eeeeeeeeee": "closed", "ffffffffff": "void", "gggggggggg": "open"}
    assert glob.glob(str(tmp_path / "journal.sqlite.bak-*")) and glob.glob(str(tmp_path / "journal_shadow.sqlite.bak-*"))
    assert "APPLIED" in JR.text(rep, True)


def test_roll_start():
    assert JR.roll_start(pd.Timestamp("2026-10-22 10:00", tz="America/New_York"), "America/New_York") == \
        pd.Timestamp("2026-10-21 17:00", tz="America/New_York")
    assert JR.roll_start(pd.Timestamp("2026-10-22 18:00", tz="America/New_York"), "America/New_York") == \
        pd.Timestamp("2026-10-22 17:00", tz="America/New_York")


def test_orphan_merge_restores_the_original_position(tmp_path):
    """The original row banked the partial and was voided by the first repair; the orphan row booked only the rest,
    in R of a trailed stop. The merge closes the original with the whole OANDA trade, the orphan becomes void."""
    cfg = _cfg(tmp_path)
    _db(cfg["storage"]["db_path"], [
        _row("cf8f0d0885", symbol="NDQ", status="void", opened="2026-10-08T10:55:06-04:00", entry=20000.0,
             initial_stop=19980.0, qty_initial=2.0),
        _row("9acd6396c9", strategy="orphan:unmanaged", status="closed", opened="2026-10-08T10:55:07-04:00",
             initial_stop=20030.0, realized=40.0, r_multiple=9.0),
    ])
    t = _t(None, open_="2026-10-08T14:55:07Z", close="20030.0", pl="112.0")      # 112 CAD = 80 USD for 2 units
    rep = asyncio.run(JR.run(cfg, True, client=Client([t]), now=NOW))
    plan = {p["id"]: p for p in rep["books"]["live"]["plan"]}
    assert plan["cf8f0d0885"]["action"] == "close" and plan["9acd6396c9"]["action"] == "void"
    con = sqlite3.connect(cfg["storage"]["db_path"])
    st = {r[0]: r[1:] for r in con.execute("SELECT id, status, realized, r_multiple FROM trades")}
    con.close()
    assert st["cf8f0d0885"] == ("closed", 80.0, 2.0) and st["9acd6396c9"][0] == "void"   # 80 / (2 × 20) = 2R
    rep = asyncio.run(JR.run(cfg, False, client=Client([t]), now=NOW))                   # idempotent
    assert not rep["books"]["live"]["plan"]


def test_oanda_multiplier_and_r_correction(tmp_path):
    from fxagents.reconcile import broker_cfg
    c = broker_cfg(copy.deepcopy(CFG))
    assert {s: c["instruments"][s]["multiplier"] for s in ("XAUUSD", "NDQ", "US30")} == {"XAUUSD": 1, "NDQ": 1, "US30": 1}
    cfg = copy.deepcopy(CFG)
    cfg["storage"]["db_path"] = str(tmp_path / "journal.sqlite")
    # closed by the first repair with the futures multiplier: gold 10 → R 10× too small
    _db(cfg["storage"]["db_path"], [_row("hhhhhhhhhh", symbol="XAUUSD", status="closed", entry=4000.0, initial_stop=3990.0,
                                         qty_initial=3.0, realized=60.0, r_multiple=0.2, exit_reason="reconciled_at_oanda",
                                         closed="2026-10-08T12:00:00-04:00")])
    rep = asyncio.run(JR.run(cfg, True, client=Client([]), now=NOW))
    assert [p["action"] for p in rep["books"]["live"]["plan"]] == ["fix_r"]
    con = sqlite3.connect(cfg["storage"]["db_path"])
    assert con.execute("SELECT r_multiple FROM trades").fetchone()[0] == 2.0       # 60 / (3 × 10 × 1)
    con.close()
    assert not asyncio.run(JR.run(cfg, False, client=Client([]), now=NOW))["books"]["live"]["plan"]


def test_reconcile_ignores_void_rows_when_matching():
    from fxagents import reconcile as R
    jr = [_row("cf8f0d0885", status="closed", opened="2026-10-08T10:55:06-04:00", realized=40.0, r_multiple=2.0,
               exit_price=20040.0, closed="2026-10-08T12:00:00-04:00"),
          _row("9acd6396c9", strategy="orphan:unmanaged", status="void", opened="2026-10-08T10:55:07-04:00")]
    t = _t(None, open_="2026-10-08T14:55:07Z")
    res = R.reconcile(R.broker_cfg(copy.deepcopy(CFG)), jr, [t], [])
    assert [p["id"] for p in res["pairs"]] == ["cf8f0d0885"] and not res["state_mismatch"] and not res["journal_only"]
