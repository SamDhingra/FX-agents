"""Oct 26 2026 — bias safety fixes: loss guards survive restarts and are per book, stale bias is refused,
Jev bias audits are bound to the reading they judged, expire, and are asked once per reading."""
import asyncio
import copy
from types import SimpleNamespace

import pandas as pd
import pytest

from fxagents.agents.context import BiasAgent, BookGuardAgent
from fxagents.agents.core import Ctx
from fxagents.agents.setup_first import ShadowState
from fxagents.agents.trading import RiskAgent
from fxagents.bus import Bus
from fxagents.models import Position, Signal
from fxagents.state import LiveState, RuntimeStore
from tests.test_core import CFG, TZ

T0 = pd.Timestamp("2026-10-26 09:05", tz=TZ)


def run(c):
    return asyncio.run(c)


def reading(label="BULLISH", h1=1, score=0.8):
    return {"score": score, "d": 1, "h4": 1, "h1": h1, "label": label, "pd_pos": 0.5, "pdh": 1.0, "pdl": 0.0,
            "asia_hi": 1.0, "asia_lo": 0.0, "h4_swing_hi": 1.0, "h4_swing_lo": 0.0, "price": 100.0}


class StubJev:
    def __init__(self, prob=0.2, fallback=False):
        self.prob, self.fallback, self.calls = prob, fallback, 0

    async def bias_audit(self, info):
        self.calls += 1
        return {"prob": self.prob, "source": "jev", "fallback": self.fallback, "error": ""}


def make_bias(tmp_path=None, jev=None, state=None, cfg=None):
    cfg = cfg or copy.deepcopy(CFG)
    cfg["instruments"] = {"NDQ": cfg["instruments"]["NDQ"]}
    st = state or LiveState(mode="paper")
    st.now = T0
    h1 = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
                      index=pd.date_range("2026-10-24", periods=14, freq="1h", tz=TZ))
    store = SimpleNamespace(h1=lambda s: h1)
    ctx = Ctx(cfg, Bus(), st, store, None, None, jev or StubJev(), None)
    a = BiasAgent(ctx)
    a.start()
    a.cur = reading()
    a.compute = lambda sym, now: dict(a.cur)
    return a, st, ctx


def pos(sym="NDQ", pnl=-10.0, mode="aligned", pid=None):
    p = Position(sym, 1, "x", 99.0, 99.0, 1.0, 1.0, T0, bias_mode=mode, realized=pnl)
    if pid:
        p.id = pid
    return p


def close(agent, p):
    run(agent.on_closed({"position": p, "price": 100.0}))


# ── 1. loss guards persist, roll with the trading day, dedupe closes ─────────────────────────────────────
def two_losses(a):
    close(a, pos(pnl=-5)); close(a, pos(pnl=-5))


def test_suspension_survives_a_restart(tmp_path):
    a, st, ctx = make_bias()
    a._roll(T0)
    st.bias["NDQ"] = reading() | {"h1": 1}
    two_losses(a)
    assert st.guards["NDQ"]["suspended"] and st.guards["NDQ"]["suspended_h1"] == 1
    store = RuntimeStore(tmp_path / "rt.json"); store.save(st)
    # restart: brand-new state + agent, restored through the same path as startup_reconcile
    a2, st2, _ = make_bias()
    store.restore(st2, T0 + pd.Timedelta(minutes=30))
    assert st2.guards["NDQ"]["suspended"] is True and st2.guards["NDQ"]["aligned_losses"] == 2
    assert a2.guard["NDQ"] is st2.guards["NDQ"]                 # the agent sees the restored dict
    a2._roll(T0 + pd.Timedelta(minutes=30))             # same trading day: the streak is not reset
    assert st2.guards["NDQ"]["aligned_losses"] == 2 and st2.guards["NDQ"]["suspended"]


def test_release_rule_unchanged_after_restore(tmp_path):
    a, st, _ = make_bias()
    a._roll(T0); st.bias["NDQ"] = reading(); two_losses(a)
    store = RuntimeStore(tmp_path / "rt.json"); store.save(st)
    a2, st2, _ = make_bias(); store.restore(st2, T0)
    a2.cur = reading(h1=1)
    run(a2.update("NDQ", T0 + pd.Timedelta(hours=1)))
    assert st2.bias["NDQ"]["suspended"] is True                 # same 1H sign → still suspended
    a2.cur = reading(h1=-1)
    run(a2.update("NDQ", T0 + pd.Timedelta(hours=2)))
    assert st2.bias["NDQ"]["suspended"] is False and st2.guards["NDQ"]["aligned_losses"] == 0


def test_streak_resets_after_the_17h_roll_but_suspension_stays(tmp_path):
    a, st, _ = make_bias()
    a._roll(T0); st.bias["NDQ"] = reading()
    close(a, pos(pnl=-5))                                       # one loss: streak 1, not suspended
    store = RuntimeStore(tmp_path / "rt.json"); store.save(st)
    a2, st2, _ = make_bias()
    store.restore(st2, pd.Timestamp("2026-10-26 18:00", tz=TZ))   # restart after the 17:00 roll
    assert st2.guards["NDQ"]["aligned_losses"] == 0
    # a suspension is kept across the roll
    st.guards["NDQ"].update(suspended=True, suspended_h1=1, aligned_losses=2); store.save(st)
    a3, st3, _ = make_bias(); store.restore(st3, pd.Timestamp("2026-10-27 08:00", tz=TZ))
    assert st3.guards["NDQ"]["suspended"] is True and st3.guards["NDQ"]["aligned_losses"] == 0


def test_the_startup_gate_does_not_wipe_the_saved_guard(tmp_path):
    from fxagents.state import STARTUP_HALT
    a, st, _ = make_bias(); a._roll(T0); st.bias["NDQ"] = reading(); two_losses(a)
    store = RuntimeStore(tmp_path / "rt.json"); store.save(st)
    fresh = LiveState(mode="paper"); fresh.halt_reason = STARTUP_HALT      # restarted, not yet restored
    store.save(fresh)
    assert store.load()["bias_guard"]["symbols"]["NDQ"]["suspended"] is True


def test_every_guard_change_is_saved(tmp_path):
    a, st, ctx = make_bias(); ctx.runtime_store = RuntimeStore(tmp_path / "rt.json")
    a._roll(T0); st.bias["NDQ"] = reading(); two_losses(a)
    assert ctx.runtime_store.load()["bias_guard"]["symbols"]["NDQ"]["suspended"] is True


def test_a_replayed_close_counts_once():
    a, st, _ = make_bias(); a._roll(T0); st.bias["NDQ"] = reading()
    p = pos(pnl=-5, pid="abc")
    close(a, p); close(a, p); close(a, pos(pnl=-5, pid="abc"))
    assert st.guards["NDQ"]["aligned_losses"] == 1 and not st.guards["NDQ"]["suspended"]
    close(a, pos(pnl=-5, pid="def"))
    assert st.guards["NDQ"]["suspended"]


def test_dedupe_ids_survive_a_restart(tmp_path):
    a, st, _ = make_bias(); a._roll(T0); st.bias["NDQ"] = reading()
    close(a, pos(pnl=-5, pid="abc"))
    store = RuntimeStore(tmp_path / "rt.json"); store.save(st)
    a2, st2, _ = make_bias(); store.restore(st2, T0); a2._roll(T0)
    close(a2, pos(pnl=-5, pid="abc"))
    assert st2.guards["NDQ"]["aligned_losses"] == 1


# ── 2. paper books keep their own guards ──────────────────────────────────────────────────────────────
def book(main):
    cfg = copy.deepcopy(CFG)
    cfg["instruments"] = {"NDQ": cfg["instruments"]["NDQ"]}
    st = ShadowState(main, mode="paper"); st.now = T0
    ctx = Ctx(cfg, Bus(), st, None, None, None, None, None)
    g = BookGuardAgent(ctx); g.start()
    return g, st


def gate(state, cfg=None):
    cfg = cfg or copy.deepcopy(CFG)
    me = SimpleNamespace(cfg=cfg, state=state, ctx=SimpleNamespace(store=None, jev=None))
    sig = Signal("NDQ", "x", 1, 100.0, 99.0, T0)
    return run(RiskAgent.bias_gate(me, sig, {"quality": 0.8}, T0))


def test_a_practice_loss_does_not_suspend_a_paper_book_and_vice_versa():
    a, main, _ = make_bias(jev=StubJev(prob=0.9)); a._roll(T0); main.bias["NDQ"] = reading() | {"updated": T0.isoformat(timespec="minutes")}
    g, sh = book(main)
    two_losses(a)                                               # practice account: suspended
    assert main.guards["NDQ"]["suspended"] and not sh.guards["NDQ"]["suspended"]
    assert "reject" in gate(main) and gate(sh)["mode"] == "aligned"
    assert gate(main)["reject"].startswith("bias suspended")
    # now the paper book loses twice while the practice account is clean
    a2, main2, _ = make_bias(jev=StubJev(prob=0.9)); a2._roll(T0); main2.bias["NDQ"] = reading() | {"suspended": False, "in_doubt": False, "aligned_losses": 0, "updated": T0.isoformat(timespec="minutes")}
    g2, sh2 = book(main2)
    for _ in range(2):
        run(g2.on_closed({"position": pos(pnl=-5), "price": 1}))
    assert sh2.guards["NDQ"]["suspended"] and not main2.guards["NDQ"]["suspended"]
    assert gate(sh2)["reject"].startswith("bias suspended") and gate(main2)["mode"] == "aligned"
    assert sh2.bias_for("NDQ")["score"] == main2.bias_for("NDQ")["score"] == 0.8     # same structural reading


def test_a_paper_book_releases_on_a_fresh_1h_break_and_persists(tmp_path):
    a, main, _ = make_bias(); main.bias["NDQ"] = reading()
    g, sh = book(main)
    sh_ctx_store = RuntimeStore(tmp_path / "sh.json"); g.ctx.runtime_store = sh_ctx_store
    for _ in range(2):
        run(g.on_closed({"position": pos(pnl=-5), "price": 1}))
    assert sh.bias_for("NDQ")["suspended"] and sh.bias_for("NDQ")["state"] == "SUSPENDED"
    run(g.on_clock(T0)); assert sh.guards["NDQ"]["suspended"]               # 1H unchanged
    main.bias["NDQ"] = reading(h1=-1)
    run(g.on_clock(T0 + pd.Timedelta(minutes=1)))
    assert not sh.guards["NDQ"]["suspended"] and not sh.bias_for("NDQ")["suspended"]
    # persisted through the book's own runtime file
    g2, sh2 = book(main)
    sh_ctx_store.restore(sh2, T0)
    assert sh2.guards["NDQ"]["aligned_losses"] == 0 and sh2.guard_closed


def test_a_book_overlay_hides_the_practice_suspension_state():
    a, main, _ = make_bias(); a._roll(T0); main.bias["NDQ"] = reading()
    run(a.update("NDQ", T0)); two_losses(a)
    assert main.bias["NDQ"]["state"] == "SUSPENDED"
    g, sh = book(main)
    assert sh.bias_for("NDQ")["state"] != "SUSPENDED" and sh.bias_for("NDQ")["suspended"] is False


# ── 3. stale bias ─────────────────────────────────────────────────────────────────────────────────────────
def test_stale_bias_is_refused():
    st = LiveState(); st.now = T0
    st.bias["NDQ"] = reading() | {"suspended": False, "in_doubt": False, "aligned_losses": 0,
                                  "updated": (T0 - pd.Timedelta(minutes=151)).isoformat(timespec="minutes")}
    out = gate(st)
    assert "bias stale: last updated 2h31m ago" in out["reject"]
    st.bias["NDQ"]["updated"] = (T0 - pd.Timedelta(minutes=149)).isoformat(timespec="minutes")
    assert gate(st)["mode"] == "aligned"
    cfg = copy.deepcopy(CFG); cfg["bias"]["max_age_min"] = 30
    assert "stale" in gate(st, cfg)["reject"]
    cfg["bias"]["max_age_min"] = 0                              # 0 switches the check off
    assert gate(st, cfg)["mode"] == "aligned"


def test_a_normal_hourly_cycle_is_never_stale():
    a, st, _ = make_bias(jev=StubJev(prob=0.9)); a.cur = reading()
    run(a.update("NDQ", T0))
    assert gate(st)["mode"] == "aligned"
    run(a.update("NDQ", T0 + pd.Timedelta(minutes=65)))
    st.now = T0 + pd.Timedelta(minutes=125)
    me = SimpleNamespace(cfg=copy.deepcopy(CFG), state=st, ctx=SimpleNamespace(store=None, jev=None))
    sig = Signal("NDQ", "x", 1, 100.0, 99.0, st.now)
    assert run(RiskAgent.bias_gate(me, sig, {"quality": 0.8}, T0 + pd.Timedelta(minutes=125)))["mode"] == "aligned"   # 60 min after the 2nd update


# ── 4. Jev audits ─────────────────────────────────────────────────────────────────────────────────────────
def test_one_audit_request_per_reading_and_one_sample_per_hour():
    jev = StubJev(prob=0.2)
    a, st, _ = make_bias(jev=jev)
    run(a.update("NDQ", T0)); run(a.update("NDQ", T0 + pd.Timedelta(minutes=20)))     # same hour, same reading
    assert jev.calls == 1 and len(a.samples["NDQ"]) == 1
    a.cur = reading(label="BEARISH", score=-0.8)                                      # the reading changes in-hour
    run(a.update("NDQ", T0 + pd.Timedelta(minutes=25)))
    assert jev.calls == 2
    run(a.update("NDQ", T0 + pd.Timedelta(hours=1)))                                   # next hour = new reading
    assert jev.calls == 3 and len(a.samples["NDQ"]) == 2


def test_in_doubt_clears_when_the_audit_expires_after_a_failed_refresh():
    jev = StubJev(prob=0.2)
    a, st, _ = make_bias(jev=jev)
    run(a.update("NDQ", T0))
    assert st.bias["NDQ"]["in_doubt"] is True
    jev.fallback = True                                        # Jev is down from now on
    run(a.update("NDQ", T0 + pd.Timedelta(hours=1)))
    assert st.bias["NDQ"]["in_doubt"] is True                  # still fresh (60 min < 180) and same label
    run(a.update("NDQ", T0 + pd.Timedelta(hours=3, minutes=5)))
    assert st.bias["NDQ"]["in_doubt"] is False and st.bias["NDQ"]["audit_p"] is None


def test_in_doubt_clears_when_the_bias_direction_changed(caplog):
    jev = StubJev(prob=0.2)
    a, st, _ = make_bias(jev=jev)
    run(a.update("NDQ", T0)); assert st.bias["NDQ"]["in_doubt"]
    jev.fallback = True
    a.cur = reading(label="BEARISH", score=-0.8)
    with caplog.at_level("INFO", logger="bias"):
        run(a.update("NDQ", T0 + pd.Timedelta(hours=1)))
    assert st.bias["NDQ"]["in_doubt"] is False
    assert any("BULLISH -> BEARISH" in r.message for r in caplog.records)


def test_a_late_audit_for_an_older_reading_does_not_overwrite_a_newer_one():
    class SlowJev:
        calls = 0
        def __init__(self): self.gates = []
        async def bias_audit(self, info):
            self.calls += 1
            ev = asyncio.Event(); self.gates.append((info["label"], ev)); await ev.wait()
            return {"prob": 0.9 if info["label"] == "BULLISH" else 0.1, "source": "jev", "fallback": False, "error": ""}
    jev = SlowJev()
    a, st, _ = make_bias(jev=jev)

    async def scenario():
        t1 = asyncio.create_task(a.update("NDQ", T0))                         # BULLISH reading, answer pending
        await asyncio.sleep(0)
        a.cur = reading(label="BEARISH", score=-0.8)
        t2 = asyncio.create_task(a.update("NDQ", T0 + pd.Timedelta(minutes=10)))   # newer reading
        await asyncio.sleep(0)
        jev.gates[1][1].set(); await t2                                      # the newer answer lands first (in doubt)
        jev.gates[0][1].set(); await t1                                      # the old one arrives late
    asyncio.run(scenario())
    g = st.guards["NDQ"]
    assert g["audit_label"] == "BEARISH" and g["audit_p"] == 0.1 and g["in_doubt"] is True
    assert st.bias["NDQ"]["label"] == "BEARISH"
