"""Retrospective backfill of the shadow review gate (Oct 27 2026): past closed trades rebuilt as of their entry minute from
(stubbed) OANDA candles, reviewed through the live path by stubbed providers, stored as source='backfill', scored apart
from the live scorecard. No network."""
import asyncio
import copy
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fxagents.agents.context import compute_bias
from fxagents.dashboard.server import build_app
from fxagents.dynamic import backfill as B
from fxagents.dynamic import packet as P
from fxagents.dynamic import providers as PR
from fxagents.dynamic import score as S
from fxagents.dynamic import store as DS
from fxagents.journal import Journal
from fxagents.state import trading_day
from tests.test_core import TZ
from tests.test_dashboard_insights import make_ctx
from tests.test_dynamic_review import SCFG, Stub, dyn_cfg, mk_packet

SERIES_START = pd.Timestamp("2026-08-15 00:00", tz=TZ)
SERIES_END = pd.Timestamp("2026-10-27 00:00", tz=TZ)
SPREAD, SPREAD_BEFORE_T1 = 0.40, 0.55

# id, side, opened, closed, R, entry, stop
TRADES = [("t1", "LONG", "2026-10-20T10:05:00-04:00", "2026-10-20T10:50:00-04:00", 1.5, 2650.0, 2648.0),
          ("t2", "LONG", "2026-10-21T09:40:00-04:00", "2026-10-21T10:30:00-04:00", -1.0, 2650.0, 2648.0),
          ("t3", "LONG", "2026-10-22T11:15:00-04:00", "2026-10-22T12:00:00-04:00", 0.8, 2650.0, 2648.0),
          ("t4", "SHORT", "2026-10-23T14:20:00-04:00", "2026-10-23T15:00:00-04:00", -1.0, 2650.0, 2652.0)]


def run(c):
    return asyncio.run(c)


def entry_of(opened):
    return pd.Timestamp(opened).tz_convert(TZ).floor("min")


POISON = {entry_of(t[2]): 9001.0 + i for i, t in enumerate(TRADES)}   # the same candles on a redo, so the packet hash matches


class FakeOanda:
    """The candles endpoint only: M1 'BA' and H1 'M' from one synthetic minute series that runs PAST every entry, with a
    poisoned price (9999) at each entry minute and a wide spread there, so any look at or beyond the entry shows up."""

    def __init__(self, poison=None):
        idx = pd.date_range(SERIES_START, SERIES_END - pd.Timedelta("1min"), freq="1min", tz=TZ)
        rng = np.random.default_rng(5)
        mid = 2650 + np.cumsum(rng.normal(0, 0.3, len(idx)))
        self.mid = pd.Series(mid, index=idx)
        self.spread = pd.Series(SPREAD, index=idx)
        for t, v in (poison or {}).items():
            self.mid[t] = v
            self.spread[t] = 99.0
        self.spread[entry_of(TRADES[0][2]) - pd.Timedelta("1min")] = SPREAD_BEFORE_T1
        self.requests: list[dict] = []
        h = self.mid.resample("1h").agg(["first", "max", "min", "last"])
        self.h1 = h

    async def req(self, method, path, *, params=None, json=None, retries=3):
        assert method == "GET" and path.endswith("/candles")
        self.requests.append(dict(params, path=path))
        gran, price = params["granularity"], params["price"]
        a, b = pd.Timestamp(params["from"]), pd.Timestamp(params["to"])
        out = []
        if gran == "M1":
            assert price == "BA"
            ix = self.mid.index[(self.mid.index >= a) & (self.mid.index < b)]
            for t in ix:
                m, s = self.mid[t], self.spread[t]
                out.append({"time": t.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.000000000Z"), "complete": True, "volume": 10,
                            "bid": {k: str(round(m - s / 2 + d, 3)) for k, d in (("o", 0), ("h", .1), ("l", -.1), ("c", 0))},
                            "ask": {k: str(round(m + s / 2 + d, 3)) for k, d in (("o", 0), ("h", .1), ("l", -.1), ("c", 0))}})
        else:
            assert gran == "H1" and price == "M"
            ix = self.h1.index[(self.h1.index >= a) & (self.h1.index < b)]
            for t in ix:
                r = self.h1.loc[t]
                out.append({"time": t.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.000000000Z"), "complete": True, "volume": 600,
                            "mid": {"o": str(r["first"]), "h": str(r["max"]), "l": str(r["min"]), "c": str(r["last"])}})
        assert len(out) <= 5000, "OANDA refuses more than 5000 candles in one answer"
        # the hour still forming at the end of the window is not complete
        if gran == "H1" and out and pd.Timestamp(out[-1]["time"]) + pd.Timedelta("1h") > b.tz_convert("UTC"):
            out[-1]["complete"] = False
        if gran == "M1" and out and pd.Timestamp(out[-1]["time"]) + pd.Timedelta("1min") > b.tz_convert("UTC"):
            out[-1]["complete"] = False
        return {"candles": out}


def journal_with_trades(tmp_path, name="j"):
    j = Journal(str(tmp_path / f"{name}.sqlite"))
    for tid, side, opened, closed, r, entry, stop in TRADES:
        j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple,realized,qty_initial,entry,initial_stop,events) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (tid, "XAUUSD", side, "macd_cross:5m@pb-x", "closed", opened, closed, r, r * 100, 100, entry, stop,
                      json.dumps([{"kind": "entry", "rr": 1.5}] + ([{"kind": "partial", "r": 2.0}] if r > 0 else []))))
    j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,entry,initial_stop,events) VALUES('open1','XAUUSD','LONG','x:5m@y','open',"
                 "'2026-10-26T10:00:00-04:00',2650,2648,'[]')")
    j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,entry,initial_stop,events) VALUES('nor','XAUUSD','LONG','x:5m@y','closed',"
                 "'2026-10-24T10:00:00-04:00','2026-10-24T11:00:00-04:00',2650,2648,'[]')")
    j.db.commit()
    return j


def bf_cfg(**kw):
    cfg = dyn_cfg(prices={"c-1": {"in_per_mtok": 2.0, "out_per_mtok": 10.0}, "o-1": {"in_per_mtok": 1.0, "out_per_mtok": 4.0}}, **kw)
    cfg["instruments"]["XAUUSD"]["oanda_instrument"] = "XAU_USD"
    return cfg


def go(tmp_path, n=4, stubs=None, cfg=None, poison=True, name="j", out=None, **kw):
    j = journal_with_trades(tmp_path, name)
    cl = FakeOanda({entry_of(t[2]): 9001.0 + i for i, t in enumerate(TRADES)} if poison else None)
    stubs = stubs if stubs is not None else {"openai": Stub("openai", "ENTER", marker="O"), "claude": Stub("claude", "ENTER", marker="C")}
    for k, st in stubs.items():
        st.prices = {"in_per_mtok": 2.0, "out_per_mtok": 10.0}
    code = run(B.run(cfg or bf_cfg(), "live", n, out or tmp_path / "out", client=cl, journal=j, providers=stubs, **kw))
    return code, j, cl, stubs


# ── 1. only data before the entry reaches the packet ───────────────────────────────────────────────────────────────
def test_only_data_before_the_entry_minute_reaches_the_packet(tmp_path):
    code, j, cl, stubs = go(tmp_path)
    assert code == 0
    for i, (tid, side, opened, *_) in enumerate(TRADES):
        ts = entry_of(opened)
        pk = json.loads(j.db.execute("SELECT packet FROM dyn_candidates WHERE candidate_id=?", (tid,)).fetchone()[0])
        c = pk["candles"]
        starts = [pd.Timestamp(r[0], tz=TZ) for k in ("m5_closed", "m15_closed", "h1_closed") for r in c[k]]
        assert starts and all(s < ts for s in starts)
        assert pd.Timestamp(c["m5_closed"][-1][0], tz=TZ) + pd.Timedelta("5min") <= ts
        assert pd.Timestamp(c["h1_closed"][-1][0], tz=TZ) + pd.Timedelta("1h") <= ts
        text = json.dumps(pk)
        assert f"{9001 + i}" not in text and '"spread": 99' not in text        # this trade's own poisoned entry minute was never read
        assert pk["candidate"]["entry_time_ny"] == ts.strftime("%Y-%m-%d %H:%M")
        if c["m15_forming"] and c["m15_forming"]["minutes_in"]:
            assert pd.Timestamp(c["m15_forming"]["start"], tz=TZ) + pd.Timedelta(minutes=c["m15_forming"]["minutes_in"]) == ts
    # nothing at or after an entry was even requested: every window ends at (or before) that trade's entry minute
    ends = {entry_of(t[2]).tz_convert("UTC") for t in TRADES}
    tos = {pd.Timestamp(r["to"]) for r in cl.requests}
    assert max(tos) == max(ends) and ends <= tos                       # each trade's windows end exactly at its entry; none goes past it
    assert any(r["granularity"] == "M1" and r["price"] == "BA" for r in cl.requests) and any(r["granularity"] == "H1" and r["price"] == "M" for r in cl.requests)


def test_a_candle_at_or_after_the_entry_is_refused_by_the_store():
    idx = pd.date_range("2026-10-20 09:00", "2026-10-20 10:05", freq="1min", tz=TZ)          # includes 10:05, the entry minute
    m1 = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)
    h1 = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=pd.date_range("2026-10-18 00:00", "2026-10-20 09:00", freq="1h", tz=TZ))
    entry = pd.Timestamp("2026-10-20 10:05", tz=TZ)
    with pytest.raises(AssertionError):
        B.RetroStore("XAUUSD", entry, m1, h1)
    with pytest.raises(AssertionError):                                                      # the 10:00 hour is still open at 10:05
        B.RetroStore("XAUUSD", entry, m1.iloc[:-1], pd.DataFrame(h1).reindex(pd.date_range("2026-10-18 00:00", "2026-10-20 10:00", freq="1h", tz=TZ)))
    ok = B.RetroStore("XAUUSD", entry, m1.iloc[:-1], h1)
    assert len(ok.m1()) == len(m1) - 1 and ok.tf("XAUUSD", "5min").index[-1] + pd.Timedelta("5min") <= entry


def test_fetch_never_asks_past_the_end_and_pages_under_the_candle_limit():
    cl = FakeOanda()
    end = pd.Timestamp("2026-10-20 10:05", tz=TZ)
    df = run(B.fetch_candles(cl, "XAU_USD", "M1", "BA", end - pd.Timedelta(days=5), end, TZ))
    assert df.index.max() == end - pd.Timedelta("1min") and len(df) == 5 * 1440 and df.index.is_monotonic_increasing
    assert len(cl.requests) >= 2 and all(pd.Timestamp(r["to"]) <= end.tz_convert("UTC") for r in cl.requests)
    assert {"open", "high", "low", "close", "bid", "ask"} <= set(df.columns) and (df["ask"] > df["bid"]).all()


# ── 2. spread, cost and the bias ───────────────────────────────────────────────────────────────────────────────────
def test_spread_cost_and_bias_come_from_the_data_before_the_entry(tmp_path):
    code, j, cl, stubs = go(tmp_path)
    pk = json.loads(j.db.execute("SELECT packet FROM dyn_candidates WHERE candidate_id='t1'").fetchone()[0])
    assert pk["order"]["spread"] == SPREAD_BEFORE_T1 and pk["order"]["stop_distance"] == 2.0
    assert pk["order"]["cost_r"] == round(SPREAD_BEFORE_T1 / 2.0, 3) and pk["order"]["entry"] == 2650.0 and pk["order"]["stop"] == 2648.0
    assert pk["order"]["target_r"] == 1.5                                 # from the entry event, never the (outcome-revealing) partial
    pk4 = json.loads(j.db.execute("SELECT packet FROM dyn_candidates WHERE candidate_id='t4'").fetchone()[0])
    assert pk4["candidate"]["side"] == "SHORT" and pk4["order"]["spread"] == SPREAD and pk4["order"]["cost_r"] == round(SPREAD / 2.0, 3)
    b = pk["bias"]
    assert b["label"] in ("BULLISH", "BEARISH", "NEUTRAL") and b["score"] is not None and b["d"] in (-1, 0, 1)
    assert b["minutes_since_update"] == 0 and b["h1_minutes"] == 60 and b["h1_complete"] is True
    assert any(v is not None for v in pk["levels"].values())
    # the same numbers as the live computation on the same H1 data
    ts = entry_of(TRADES[0][2])
    h1 = run(B.fetch_candles(FakeOanda(), "XAU_USD", "H1", "M", ts - pd.Timedelta(days=60), ts, TZ))
    h1 = h1[h1.index + pd.Timedelta("1h") <= ts][["open", "high", "low", "close"]]
    m1 = run(B.fetch_candles(FakeOanda(), "XAU_USD", "M1", "BA", ts - pd.Timedelta(days=5), ts, TZ))
    cfg = bf_cfg()
    want = compute_bias(h1, ts, float(m1["close"].iloc[-1]), cfg["bias"]["weights"], cfg["bias"]["min_align"])
    assert (b["label"], b["score"], b["d"], b["h4"], b["h1"]) == (want["label"], round(want["score"], 3), want["d"], want["h4"], want["h1"])
    assert pk["levels"]["pdh"] == round(want["pdh"], 2)
    # the setup record is what was known then: closed trades of the setup that had closed before t1's entry (none)
    assert pk["setup_record"] is None
    assert json.loads(j.db.execute("SELECT packet FROM dyn_candidates WHERE candidate_id='t4'").fetchone()[0])["setup_record"]["trades"] == 3


# ── 3. which trades ────────────────────────────────────────────────────────────────────────────────────────────────
def test_picks_the_newest_closed_unreviewed_trades_and_skips_reviewed_ones(tmp_path):
    j = journal_with_trades(tmp_path)
    DS.ensure_schema(j)
    cfg = bf_cfg()
    got, notes = B.pick_trades(j, cfg, 3)
    assert [t["id"] for t in got] == ["t4", "t3", "t2"]                    # open and r_multiple-less rows never; newest close first
    DS.add_candidate(j, {"candidate": {"id": "t3", "book": "live", "symbol": "XAUUSD", "side": "LONG", "strategy": "s", "entry_time_utc": "2026-10-22 15:15"},
                         "packet_hash": "h"}, "reviewed", "dyn-v1")
    got, _ = B.pick_trades(j, cfg, 3)
    assert [t["id"] for t in got] == ["t4", "t2", "t1"]                    # t3 has a review already
    code, j2, cl, stubs = go(tmp_path, n=2, name="k")
    assert code == 0
    assert {r[0] for r in j2.db.execute("SELECT candidate_id FROM dyn_candidates")} == {"t4", "t3"}
    # a second run picks the next two, and never repeats a reviewed one
    run(B.run(cfg, "live", 4, tmp_path / "o2", client=FakeOanda(), journal=j2, providers={"claude": Stub("claude"), "openai": Stub("openai")}))
    assert {r[0] for r in j2.db.execute("SELECT candidate_id FROM dyn_candidates")} == {"t1", "t2", "t3", "t4"}
    assert j2.db.execute("SELECT COUNT(*) FROM dyn_reviews WHERE candidate_id='t4' AND round=1").fetchone()[0] == 2


def test_redo_redoes_any_abstained_round1_keeps_live_rows_and_real_answers(tmp_path):
    abst = {"openai": Stub("openai", "ABSTAIN"), "claude": Stub("claude", "ABSTAIN")}
    code, j, cl, _ = go(tmp_path, n=4, stubs=abst)
    assert code == 0
    q = lambda sql, *a: [tuple(r) for r in j.db.execute(sql, a).fetchall()]
    assert {r[0] for r in q("SELECT DISTINCT action FROM dyn_reviews")} == {"ABSTAIN"}
    j.db.execute("UPDATE dyn_reviews SET action='WAIT' WHERE candidate_id='t3' AND provider='claude' AND round=1")   # t3: one real answer
    j.db.execute("UPDATE dyn_candidates SET source='live', retrospective=0 WHERE candidate_id='t2'")                # t2: a live row
    j.db.commit()
    live_before = q("SELECT * FROM dyn_reviews WHERE candidate_id='t2' ORDER BY provider, round")
    cfg = bf_cfg()
    assert B.pick_trades(j, cfg, 4)[0] == []                       # without --redo nothing is picked
    assert [t["id"] for t in B.pick_trades(j, cfg, 4, redo=True)[0]] == ["t4", "t3", "t1"]
    assert B.redoable_ids(j) == {"t1", "t3", "t4"}                # t3 too: OpenAI's round 1 is still a non-answer
    ok = {"openai": Stub("openai", "ENTER", marker="O"), "claude": Stub("claude", "ENTER", marker="C")}
    run(B.run(cfg, "live", 4, tmp_path / "o", dry_run=True, client=FakeOanda(POISON), journal=j, providers=ok, redo=True))
    assert q("SELECT COUNT(*) FROM dyn_reviews WHERE candidate_id IN ('t1','t4') AND action='ENTER'")[0][0] == 0   # dry run changes nothing
    assert not ok["openai"].seen and not ok["claude"].seen
    run(B.run(cfg, "live", 4, tmp_path / "o", client=FakeOanda(POISON), journal=j, providers=ok, redo=True))
    for tid in ("t1", "t4"):
        assert {r[0] for r in q("SELECT action FROM dyn_reviews WHERE candidate_id=? AND round=1", tid)} == {"ENTER"}
        assert q("SELECT source FROM dyn_candidates WHERE candidate_id=?", tid) == [("backfill",)]
    # t3: Claude's WAIT is kept and not paid twice; OpenAI is asked again; both valid, so the exchange ran
    assert q("SELECT action FROM dyn_reviews WHERE candidate_id='t3' AND provider='claude' AND round=1") == [("WAIT",)]
    assert q("SELECT action FROM dyn_reviews WHERE candidate_id='t3' AND provider='openai' AND round=1") == [("ENTER",)]
    assert len(ok["claude"].seen) == 2 and len(ok["openai"].seen) == 3            # t1,t4 for Claude; t1,t3,t4 for OpenAI
    assert q("SELECT exchange_status FROM dyn_candidates WHERE candidate_id='t3'") == [("done",)]
    assert q("SELECT COUNT(*) FROM dyn_reviews WHERE candidate_id='t3' AND round=2")[0][0] == 2
    assert q("SELECT * FROM dyn_reviews WHERE candidate_id='t2' ORDER BY provider, round") == live_before
    assert "t2" not in B.redoable_ids(j) and B.clear_backfill(j, ["t2"]) == 0
    assert q("SELECT COUNT(*) FROM dyn_candidates WHERE candidate_id='t2'")[0][0] == 1


def test_redo_with_openai_enter_and_claude_abstain_calls_only_claude_then_runs_the_exchange(tmp_path):
    first = {"openai": Stub("openai", "ENTER", marker="O"), "claude": Stub("claude", "ABSTAIN")}
    code, j, cl, _ = go(tmp_path, n=1, stubs=first)
    cid = "t4"
    q = lambda sql, *a: [tuple(r) for r in j.db.execute(sql, a).fetchall()]
    assert q("SELECT exchange_status FROM dyn_candidates WHERE candidate_id=?", cid)[0][0].startswith("skipped")
    # stale round-2 rows and exchange fields from an earlier run must go too
    j.db.execute("INSERT INTO dyn_reviews(candidate_id,provider,model,prompt_version,packet_hash,action,called,round) "
                 "VALUES(?,?,?,?,?,?,?,?)", (cid, "openai", "x", "dyn-x1", "h", "CANCEL", 1, 2))
    j.db.commit()
    ok = {"openai": Stub("openai", "ENTER", marker="O"), "claude": Stub("claude", "ENTER", marker="C")}
    stored = B.stored_answers(j, cid)
    assert set(stored) == {"openai"} and stored["openai"]["action"] == "ENTER" and stored["openai"]["evidence"] == "O evidence"
    code = run(B.run(bf_cfg(), "live", 1, tmp_path / "o", client=FakeOanda(POISON), journal=j, providers=ok, redo=True))
    assert code == 0
    assert ok["openai"].seen == [] and len(ok["claude"].seen) == 1                 # OpenAI round 1 not re-called
    assert len(ok["openai"].seen2) == 1 and len(ok["claude"].seen2) == 1           # the exchange ran, both saw the other's answer
    assert ok["claude"].seen2[0][2]["decisive_evidence"] == "O evidence"
    assert q("SELECT action FROM dyn_reviews WHERE candidate_id=? AND round=1 ORDER BY provider", cid) == [("ENTER",), ("ENTER",)]
    assert q("SELECT action, model FROM dyn_reviews WHERE candidate_id=? AND round=2 ORDER BY provider", cid) == [("ENTER", "stub"), ("ENTER", "stub")]
    assert q("SELECT exchange_status, exchange_decision FROM dyn_candidates WHERE candidate_id=?", cid) == [("done", "enter")]


def test_backfill_report_and_table_show_abstain_reasons(tmp_path):
    stubs = {"openai": Stub("openai", "ENTER", marker="O"), "claude": Stub("claude", "ENTER", marker="C")}

    async def boom(packet_json, candidate_id):
        return PR.abstain("HTTP 400: " + "x" * 400)
    stubs["claude"].review = boom
    out = tmp_path / "rep"
    code, j, cl, _ = go(tmp_path, n=2, stubs=stubs, out=out)
    md = (out / "report.md").read_text()
    assert "Why claude did not answer" in md and "| ABSTAIN | HTTP 400: x" in md and "| 2 |" in md
    assert max(len(l) for l in md.splitlines() if "HTTP 400" in l and l.startswith("| ABSTAIN")) < 200
    assert "ABSTAIN: HTTP 400" in md                                                # the per-trade table, short form
    ab = S.abstain_reasons(j, source="backfill")
    assert ab["claude"][0]["count"] == 2 and len(ab["claude"][0]["reason"]) <= 160 and S.abstain_reasons(j) == {}
    assert S.scorecard(j, bf_cfg(), "live")["retrospective"]["abstain"] == ab


def test_more_than_fifty_is_refused_before_anything_is_fetched(tmp_path, capsys):
    j = journal_with_trades(tmp_path)
    cl = FakeOanda()
    assert run(B.run(bf_cfg(), "live", 51, tmp_path / "o", client=cl, journal=j, providers={"claude": Stub("claude")})) == 2
    assert "refused" in capsys.readouterr().out and cl.requests == []
    assert j.db.execute("SELECT name FROM sqlite_master WHERE name='dyn_candidates'").fetchone() is None     # not even the tables
    assert B.main(["--last", "51"]) == 2 and B.main(["--last", "0"]) == 2
    with pytest.raises(ValueError):
        B.pick_trades(j, bf_cfg(), 51)
    assert B.MAX_TRADES == 50


# ── 4. the models are told nothing, rows are stored apart ─────────────────────────────────────────────────────────
def test_the_models_text_has_no_retrospective_marker_and_the_live_format(tmp_path):
    code, j, cl, stubs = go(tmp_path)
    live_keys = set(mk_packet()[0])
    seen = stubs["claude"].seen + stubs["openai"].seen + [x[0] for x in stubs["claude"].seen2 + stubs["openai"].seen2]
    assert len(seen) == 16                                                    # 4 trades x 2 providers x 2 rounds
    for text in seen:
        low = text.lower()
        assert "retro" not in low and "backfill" not in low and "reviewed_at" not in low and "past trade" not in low
        assert set(json.loads(text)) == live_keys
    row = dict(j.db.execute("SELECT * FROM dyn_candidates WHERE candidate_id='t1'").fetchone())
    assert row["source"] == "backfill" and row["retrospective"] == 1 and row["reviewed_at"]
    assert row["status"] == "reviewed" and row["prompt_version"] == "dyn-v1" and row["exchange_status"] == "done" and row["exchange_decision"] == "enter"
    stored = json.loads(row["packet"])
    assert "retrospective" not in stored and "reviewed_at" not in stored
    assert P.canonical(stored) in seen                                        # byte-identical to what the models were shown
    assert row["packet_hash"] == stored["packet_hash"] == P.packet_hash(stored)
    # same tables, both rounds, the daily budget counted on the day the calls were made
    rv = [dict(r) for r in j.db.execute("SELECT * FROM dyn_reviews WHERE candidate_id='t1' ORDER BY round, provider")]
    assert [(r["provider"], r["round"]) for r in rv] == [("claude", 1), ("openai", 1), ("claude", 2), ("openai", 2)]
    assert {r["day"] for r in rv} <= {trading_day(pd.Timestamp.now(tz=TZ)), trading_day(pd.Timestamp.now(tz=TZ) - pd.Timedelta("1min"))}
    assert DS.calls_on(j, "claude", rv[0]["day"]) == 8 and all(r["called"] == 1 for r in rv)


def test_the_daily_budget_counter_is_the_live_one(tmp_path):
    code, j, cl, stubs = go(tmp_path, cfg=bf_cfg(daily_call_budget=3))
    rows = [dict(r) for r in j.db.execute("SELECT * FROM dyn_reviews WHERE provider='claude' ORDER BY id")]
    assert sum(r["called"] for r in rows) == 3
    assert [r["action"] for r in rows].count("NOT_REVIEWED") == len(rows) - 3
    assert all(r["error"].startswith("not_reviewed: budget") for r in rows if r["action"] == "NOT_REVIEWED")


def test_live_scorecard_excludes_backfill_and_the_retrospective_section_has_it(tmp_path):
    code, j, cl, stubs = go(tmp_path, stubs={"openai": Stub("openai", "CANCEL"), "claude": Stub("claude", "ENTER")})
    # one live reviewed trade beside them
    j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple,realized,qty_initial,entry,initial_stop,events) "
                 "VALUES('live1','XAUUSD','LONG','x:5m@y','closed','2026-10-19T10:00:00-04:00','2026-10-19T11:00:00-04:00',2.0,200,100,2650,2648,'[]')")
    DS.add_candidate(j, {"candidate": {"id": "live1", "book": "live", "symbol": "XAUUSD", "side": "LONG", "strategy": "x:5m@y",
                                       "entry_time_utc": "2026-10-19 14:00"}, "packet_hash": "h"}, "reviewed", "dyn-v1")
    for prov in ("openai", "claude"):
        DS.add_review(j, "live1", prov, "m", "dyn-v1", "h", PR.result("ENTER", None, latency_ms=900, cost_usd=0.5, tokens_in=1, tokens_out=1), True, "2026-10-19", "t")
    assert DS.source_of(j, "live1") == "live" and DS.source_of(j, "t1") == "backfill" and DS.source_of(j, "nope") is None
    sc = S.scorecard(j, SCFG, "live")
    assert sc["candidates"] == 1 and sc["arms"]["A"]["total_r"] == 2.0 and sc["arms"]["D"]["total_r"] == 2.0
    assert sc["spend"]["claude"]["reviews"] == 1 and sc["spend"]["claude"]["cost_usd"] == 0.5          # backfill calls are not in the live spend
    assert "exchange" in sc and sc["exchange"]["candidates"] == 1 and sc["exchange"]["exchanged"] == 0
    rt = sc["retrospective"]
    assert rt["candidates"] == 4 and rt["reviewed_candidates"] == 4 and rt["title"] == S.RETRO_TITLE
    assert rt["arms"]["A"]["total_r"] == pytest.approx(0.3)                                              # every past entry taken
    assert rt["arms"]["C"]["total_r"] == rt["arms"]["A"]["total_r"] and rt["arms"]["B"]["total_r"] == 0.0     # Claude ENTER everywhere, OpenAI CANCEL
    assert rt["arms"]["D"]["total_r"] == 0.0 and rt["exchange"]["exchanged"] == 4
    assert rt["exchange"]["arms"]["E3"]["entered"] == 0 and rt["exchange"]["latency"] is None
    for a in "BCD":                                                                                     # no latency, no decision-rule verdict
        m = rt["arms"][a]
        assert m["latency_ms"] is None and m["share_within_30s"] is None and m["rule"] is None
    assert rt["spend"]["claude"]["calls"] == 4 and rt["spend"]["claude"]["cost_usd"] == pytest.approx(0.01 * 4)
    assert rt["spend_r2"]["openai"]["calls"] == 4
    assert S.collect(j, SCFG, "live") and all(r["id"] == "live1" for r in S.collect(j, SCFG, "live"))
    assert {r["id"] for r in S.collect(j, SCFG, "live", source="backfill")} == {"t1", "t2", "t3", "t4"}
    md = S.report_md({"All books": sc}, "dyn-v1", ["live"], [], rt)
    assert S.RETRO_TITLE in md and "never pooled" in md and "not counted" in md
    live_part = md.split(S.RETRO_TITLE)[0]
    assert "| 1 closed candidate" not in live_part and "1 closed candidate(s)." in live_part
    # the recent list says which source each review has
    assert {r["source"] for r in S.recent_reviews(j, 100)} == {"live", "backfill"}


def test_an_old_database_without_the_source_column_reads_as_all_live_and_is_migrated(tmp_path):
    p = tmp_path / "old.sqlite"
    j = Journal(str(p))
    j.db.executescript("""CREATE TABLE dyn_candidates(candidate_id TEXT PRIMARY KEY, book TEXT, symbol TEXT, side TEXT, strategy TEXT, ts TEXT,
        packet_hash TEXT, packet TEXT, status TEXT, prompt_version TEXT);
        CREATE TABLE dyn_reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT, provider TEXT, model TEXT, prompt_version TEXT, packet_hash TEXT,
        action TEXT, trigger_id TEXT, invalidation_id TEXT, evidence TEXT, conflicting TEXT, missing TEXT, latency_ms REAL, tokens_in INTEGER, tokens_out INTEGER,
        cost_usd REAL, error TEXT, called INTEGER, day TEXT, response TEXT, ts TEXT, UNIQUE(candidate_id, provider, prompt_version));""")
    j.db.execute("INSERT INTO trades(id,symbol,side,strategy,status,opened,closed,r_multiple,realized,qty_initial,entry,initial_stop,events) "
                 "VALUES('o1','XAUUSD','LONG','x','closed','2026-10-19T10:00:00-04:00','2026-10-19T11:00:00-04:00',1.0,100,100,2650,2648,'[]')")
    j.db.execute("INSERT INTO dyn_candidates(candidate_id,book,symbol,side,strategy,ts,packet_hash,packet,status,prompt_version) VALUES('o1','live','XAUUSD','LONG','x','2026-10-19 14:00','h','{}','reviewed','dyn-v1')")
    j.db.commit()
    ro = S.ReadOnly(str(p))
    assert len(S.collect(ro, SCFG, "live")) == 1 and S.collect(ro, SCFG, "live", source="backfill") == []
    sc = S.scorecard(ro, SCFG, "live")
    assert sc["candidates"] == 1 and sc["retrospective"]["candidates"] == 0 and sc["retrospective"]["reviewed_candidates"] == 0
    assert DS.source_of(ro, "o1") is None
    DS.ensure_schema(j)
    assert j.db.execute("SELECT source, retrospective FROM dyn_candidates").fetchone()[:] == ("live", 0)      # existing rows are live
    DS.add_candidate(j, {"candidate": {"id": "n", "book": "live", "symbol": "X", "side": "LONG", "strategy": "s", "entry_time_utc": "2026-10-20 14:00"},
                         "packet_hash": "h"}, "pending", "dyn-v1")
    assert DS.source_of(j, "n") == "live"
    with pytest.raises(ValueError):
        DS.add_candidate(j, {"candidate": {"id": "z", "book": "live", "symbol": "X", "side": "LONG", "strategy": "s", "entry_time_utc": "x"},
                             "packet_hash": "h"}, "pending", "dyn-v1", source="other")


# ── 5. Claude only, the table, the report ─────────────────────────────────────────────────────────────────────────
def test_without_openai_it_runs_claude_only_and_says_so(tmp_path, capsys):
    cfg = bf_cfg(openai_model="")
    code, j, cl, stubs = go(tmp_path, n=2, stubs={"claude": Stub("claude", "ENTER", marker="C")}, cfg=cfg)
    out = capsys.readouterr().out
    assert code == 0 and "OpenAI is not configured" in out and "Claude only" in out
    assert not [r for r in j.db.execute("SELECT 1 FROM dyn_reviews WHERE provider='openai'")]
    c = dict(j.db.execute("SELECT * FROM dyn_candidates WHERE candidate_id='t4'").fetchone())
    assert c["exchange_status"].startswith("skipped: needs both reviewers") and c["exchange_decision"] is None
    assert stubs["claude"].seen2 == [] and len(stubs["claude"].seen) == 2
    assert "| Claude r1 |" in out and "skipped: needs both reviewers" in out
    # configured but no key in the environment: that arm is left out (no calls, no rows) with a note
    (tmp_path / "k").mkdir()
    code, j2, cl, stubs = go(tmp_path / "k", n=1, stubs={"openai": Stub("openai", key=False), "claude": Stub("claude")})
    assert "No OPENAI_KEY in the environment" in capsys.readouterr().out
    assert not [r for r in j2.db.execute("SELECT 1 FROM dyn_reviews WHERE provider='openai'")]
    # nobody to ask
    (tmp_path / "n").mkdir()
    code, *_ = go(tmp_path / "n", n=1, stubs={"claude": Stub("claude", key=False)})
    assert code == 1 and "nothing to review with" in capsys.readouterr().out


def test_cost_estimate_and_trade_list_are_printed_before_the_calls_and_dry_run_calls_nothing(tmp_path, capsys):
    code, j, cl, stubs = go(tmp_path, n=2, dry_run=True)
    out = capsys.readouterr().out
    assert code == 0 and stubs["claude"].seen == [] and stubs["openai"].seen == []
    assert "Cost estimate" in out and "up to 4 calls" in out and "about $" in out and "t4" in out and "t3" in out and "t1" not in out
    assert "nothing was called" in out and j.db.execute("SELECT COUNT(*) FROM dyn_candidates").fetchone()[0] == 0
    assert not (tmp_path / "out" / "report.md").exists()
    # the order: list, estimate, then the reviews, then the table
    (tmp_path / "r").mkdir()
    go(tmp_path / "r", n=2)
    out = capsys.readouterr().out
    assert out.index("t4 ") < out.index("Cost estimate") < out.index("Reviewing") < out.index("| symbol |")
    # estimate arithmetic: priced from the configured per-token prices, upper bound of both rounds
    est = B.estimate(j, {"claude": Stub("claude", model="c-1"), "openai": Stub("openai", model="o-1")}, [mk_packet()[0]] * 3, {}, 120)
    assert est["providers"]["claude"]["calls"] == 6                       # 3 trades x (round 1 + round 2)
    one = B.estimate(j, {"claude": Stub("claude")}, [mk_packet()[0]] * 3, {"claude": 119}, 120)
    assert one["providers"]["claude"]["calls"] == 3 and one["providers"]["claude"]["over_budget"] is True and one["two_rounds"] is False


def test_per_trade_table_and_report_file(tmp_path, capsys):
    stubs = {"openai": Stub("openai", "ENTER", marker="O"), "claude": Stub("claude", "WAIT", marker="C")}
    stubs["claude"].action2 = "ENTER"
    out = tmp_path / "dynamic_backfill"
    code, j, cl, stubs = go(tmp_path, n=2, stubs=stubs, out=out)
    rows = B.trade_rows(j, [{"trade": {"id": "t4", "symbol": "XAUUSD", "side": "SHORT", "r_multiple": -1.0}, "entry_ts": entry_of(TRADES[3][2])}], TZ)
    r = rows[0]
    assert (r["claude_r1"], r["claude_r2"], r["openai_r1"], r["openai_r2"], r["exchange"]) == ("WAIT", "ENTER", "ENTER", "ENTER", "enter")
    assert r["cost_usd"] == pytest.approx(0.01 + 0.01 + 0.02 + 0.02) and r["entry_time"] == "2026-10-23 14:20" and r["r"] == -1.0
    md = (out / "report.md").read_text()
    assert md.startswith("# Retrospective review of past trades")
    assert "| symbol | side | entry (NY) | actual R | Claude r1 | Claude r2 | OpenAI r1 | OpenAI r2 | exchange | cost USD |" in md
    assert "| XAUUSD | SHORT | 2026-10-23 14:20 | -1.00 | WAIT | ENTER | ENTER | ENTER | enter | 0.0600 |" in md
    assert "| XAUUSD | LONG | 2026-10-22 11:15 | +0.80 |" in md
    assert "The models were not told it was a past trade" in md and S.RETRO_TITLE in md and "M1 bid/ask candles (price BA" in md
    assert "Cost estimate before the calls" in md and "Actual cost: $0.1200" in md
    summary = json.loads((out / "summary.json").read_text())
    assert summary["book"] == "live" and len(summary["trades"]) == 2 and summary["actual_usd"] == pytest.approx(0.12)
    assert "| XAUUSD | SHORT | 2026-10-23 14:20 |" in capsys.readouterr().out


def test_a_trade_that_cannot_be_rebuilt_is_skipped_with_a_reason(tmp_path, capsys):
    j = journal_with_trades(tmp_path)

    class Gappy(FakeOanda):
        async def req(self, method, path, **kw):
            p = kw["params"]
            e4 = entry_of(TRADES[3][2])
            if p["granularity"] == "M1" and (pd.Timestamp(p["to"]) == e4.tz_convert("UTC") or pd.Timestamp(p["from"]) == (e4 - pd.Timedelta(days=5)).tz_convert("UTC")):
                return {"candles": []}
            return await super().req(method, path, **kw)
    st = {"claude": Stub("claude")}
    assert run(B.run(bf_cfg(openai_model=""), "live", 3, tmp_path / "o", client=Gappy(), journal=j, providers=st)) == 0
    out = capsys.readouterr().out
    assert "SKIPPED" in out and "no M1 candles before the entry" in out
    assert {r[0] for r in j.db.execute("SELECT candidate_id FROM dyn_candidates")} == {"t3", "t2"}
    assert j.db.execute("SELECT COUNT(*) FROM dyn_candidates WHERE candidate_id='t4'").fetchone()[0] == 0
    assert "t4" in (tmp_path / "o" / "report.md").read_text()


# ── 6. dashboard ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_dashboard_shows_the_backfill_apart_and_labels_the_story(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.book_key = "live"
    j = ctx.journal
    DS.ensure_schema(j)
    DS.add_candidate(j, {"candidate": {"id": "recent", "book": "live", "symbol": "XAUUSD", "side": "LONG", "strategy": "trend_breakout:15m@pb-x",
                                       "entry_time_utc": "2026-10-14 13:00"}, "packet_hash": "h"}, "reviewed", "dyn-v1", source="backfill",
                      reviewed_at="2026-10-27T09:00:00-04:00")
    DS.set_exchange(j, "recent", "done", 21500, "enter")
    for prov in ("claude", "openai"):
        DS.add_review(j, "recent", prov, "m", "dyn-v1", "h", PR.result("ENTER", None, evidence=f"{prov} r1", conflicting="b", latency_ms=4200, cost_usd=0.01,
                                                                      tokens_in=1, tokens_out=1), True, "2026-10-27", "2026-10-27T09:00:00-04:00")
        DS.add_review(j, "recent", prov, "m", "dyn-x1", "h", PR.result("ENTER", None, evidence=f"{prov} r2", conflicting="b", latency_ms=6000, cost_usd=0.02,
                                                                      tokens_in=1, tokens_out=1, changed=False, why_changed="w"),
                      True, "2026-10-27", "2026-10-27T09:00:10-04:00", 2)
    c = TestClient(build_app(ctx))
    d = c.get("/api/dynamic").json()
    assert d["candidates"] == 0 and d["arms"]["A"]["candidates"] == 0       # nothing live
    rt = d["retrospective"]
    assert rt["candidates"] == 1 and rt["reviewed_candidates"] == 1 and rt["title"].startswith("Past trades (retrospective")
    assert rt["arms"]["D"]["total_r"] == 0.5 and rt["arms"]["D"]["latency_ms"] is None and rt["exchange"]["exchanged"] == 1
    assert {r["source"] for r in d["recent"]} == {"backfill"}
    s = c.get("/api/story/recent").json()
    assert s["shadow_source"] == "backfill" and len(s["shadow_reviews"]) == 4
    html = (Path(__file__).parents[1] / "fxagents/dashboard/static/index.html").read_text()
    assert "retrospective review" in html and "shadow_source" in html and "d.retrospective" in html
    assert "not counted toward the decision rule; latency not meaningful" in html


def test_fx_sh_has_the_command_and_the_docs_mention_it():
    root = Path(__file__).parents[1]
    sh = (root / "fx.sh").read_text()
    assert "dynbackfill)" in sh and "python -m fxagents.dynamic.backfill --book" in sh and "dynbackfill [book] [n]" in sh
    assert "--redo" in sh and "redo|--redo" in sh
    assert "dynbackfill" in (root / "docs/dynamic_controller.md").read_text()


def test_target_r_never_comes_from_a_partial_exit():
    """Oct 28 2026: a partial is only logged when the target was reached, so it revealed the outcome."""
    assert B.target_r_of(json.dumps([{"kind": "partial", "r": 2.0}])) is None
    assert B.target_r_of(json.dumps([{"kind": "entry", "rr": 1.2}, {"kind": "partial", "r": 1.2}])) == 1.2
    assert B.target_r_of(None) is None


def test_packet_says_so_on_an_m15_boundary_and_without_a_target():
    idx = pd.date_range("2026-10-20 08:00", "2026-10-20 09:59", freq="1min", tz=TZ)
    m1 = pd.DataFrame({"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 1.0}, index=idx)
    f = P.forming_m15(m1, pd.Timestamp("2026-10-20 10:00", tz=TZ), 2)
    assert f["partial"] is False and f["minutes_in"] == 0 and f["ohlc"] is None and "boundary" in f["note"]
    assert P.forming_m15(m1.iloc[:0], pd.Timestamp("2026-10-20 10:00", tz=TZ), 2) is None


def test_fresh_reviews_backfilled_trades_again_and_archives_the_old_rows(tmp_path):
    code, j, cl, stubs = go(tmp_path)
    assert code == 0
    live = mk_packet()[0]
    live["candidate"]["id"] = "live9"
    DS.add_candidate(j, live, "reviewed", "dyn-v1")                                  # a live row: never touched
    j.db.execute("CREATE TABLE IF NOT EXISTS dyn_postmortems(candidate_id TEXT, provider TEXT, why_lost TEXT)")
    j.db.execute("INSERT INTO dyn_postmortems VALUES('t2','claude','old')")
    j.db.commit()
    # dry: nothing archived, nothing called
    seen_before = len(stubs["claude"].seen)
    assert run(B.run(bf_cfg(), "live", 4, tmp_path / "o2", client=FakeOanda(), journal=j, providers=stubs, dry_run=True, fresh=True)) == 0
    assert len(stubs["claude"].seen) == seen_before and j.db.execute("SELECT COUNT(*) FROM dyn_candidates").fetchone()[0] == 5
    # without fresh: nothing left to backfill
    assert run(B.run(bf_cfg(), "live", 4, tmp_path / "o2", client=FakeOanda(), journal=j, providers=stubs)) == 0
    assert len(stubs["claude"].seen) == seen_before
    assert run(B.run(bf_cfg(), "live", 4, tmp_path / "o2", client=FakeOanda(), journal=j, providers=stubs, fresh=True)) == 0
    assert len(stubs["claude"].seen) == seen_before + 4
    arch = j.db.execute("SELECT tbl, COUNT(DISTINCT candidate_id) FROM dyn_archive GROUP BY tbl").fetchall()
    assert dict(arch) == {"dyn_candidates": 4, "dyn_reviews": 4, "dyn_postmortems": 1}
    assert j.db.execute("SELECT COUNT(*) FROM dyn_postmortems").fetchone()[0] == 0
    assert j.db.execute("SELECT source FROM dyn_candidates WHERE candidate_id='live9'").fetchone()[0] == "live"
    assert {r[0] for r in j.db.execute("SELECT candidate_id FROM dyn_candidates WHERE source='backfill'")} == {"t1", "t2", "t3", "t4"}
    assert not j.db.execute("SELECT 1 FROM dyn_archive WHERE candidate_id='live9'").fetchone()
