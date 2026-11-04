"""Several shadow books side by side: mode list, journal paths, and the dashboard's book routing."""
from fxagents.agents.setup_first import shadow_db_for, shadow_modes
from fxagents.config import load_config
from fxagents.dashboard.server import shadow_of


def _cfg(**sh):
    cfg = load_config()
    cfg["selector"]["mode"] = "hourly_pick"
    cfg["storage"]["db_path"] = "data/journal.sqlite"
    cfg["shadow"] = {"enabled": True, **sh}
    return cfg


def test_modes_list_and_legacy_single_mode():
    assert shadow_modes(_cfg(modes=["playbook", "setup_first"])) == ["playbook", "setup_first"]
    assert shadow_modes(_cfg(mode="playbook")) == ["playbook"]
    assert shadow_modes(_cfg()) == ["setup_first"]                      # default vs an hourly-pick real book
    assert shadow_modes(_cfg(modes=["hourly_pick", "playbook", "playbook", "nope"])) == ["playbook"]  # no dup of live
    c = _cfg(modes=["playbook"]); c["shadow"]["enabled"] = False
    assert shadow_modes(c) == []


def test_journal_paths_keep_existing_file_for_first_book():
    c = _cfg(modes=["playbook", "setup_first"], db_path="data/journal_playbook.sqlite")
    assert shadow_db_for(c, "playbook", True) == "data/journal_playbook.sqlite"
    assert shadow_db_for(c, "setup_first", False) == "data/journal_setup_first.sqlite"
    c = _cfg(modes=["setup_first", "playbook"])
    assert shadow_db_for(c, "setup_first", True) == "data/journal_shadow.sqlite"
    c["shadow"]["db_paths"] = {"playbook": "x.sqlite"}
    assert shadow_db_for(c, "playbook", False) == "x.sqlite"


def test_dashboard_book_routing():
    class C:  # noqa: D401 — minimal stand-in for Ctx
        pass
    a, b, ctx = C(), C(), C()
    ctx.shadows = {"playbook": a, "setup_first": b}
    ctx.shadow = a
    assert shadow_of(ctx, "setup_first") is b
    assert shadow_of(ctx, "shadow") is a           # older links/bookmarks
    assert shadow_of(ctx, "live") is None and shadow_of(ctx, None) is None and shadow_of(ctx, "x") is None


def test_allhours_and_nobias_books():
    """Oct 29 2026: playbook_allhours = entries 20:00 → 15:50 (own copy of the config); playbook_nobias = bias rule off."""
    import asyncio
    from types import SimpleNamespace

    import pandas as pd

    from fxagents.agents.setup_first import book_cfg
    from fxagents.agents.trading import RiskAgent, TraderAgent
    from fxagents.models import Signal
    c = _cfg(modes=["playbook", "playbook_allhours", "playbook_nobias"])
    assert shadow_modes(c) == ["playbook", "playbook_allhours", "playbook_nobias"]
    a = book_cfg(c, "playbook_allhours")
    assert a["sessions"]["entry_windows"] == [["20:00", "23:59"], ["00:00", "15:50"]]
    assert c["sessions"]["entry_windows"] != a["sessions"]["entry_windows"]          # the main config is untouched
    assert book_cfg(c, "playbook_nobias") is c
    t0 = pd.Timestamp("2026-10-29 10:00", tz="America/New_York")
    st = SimpleNamespace(bias_for=lambda s: {"score": -0.6, "suspended": True, "aligned_losses": 2, "label": "BEARISH"})
    sig = Signal("NDQ", "x", 1, 100.0, 99.0, t0)
    me = SimpleNamespace(cfg=c, state=st, ctx=SimpleNamespace(ignore_bias=True), now=lambda: t0)
    g = asyncio.run(RiskAgent.bias_gate(me, sig, {"quality": 0.5}, t0))
    assert g == {"mode": "ignored:counter", "risk_mult": 1.0, "score": -0.6}
    assert TraderAgent.bias_precheck(me, sig) is None
    me.ctx.ignore_bias = False
    assert asyncio.run(RiskAgent.bias_gate(me, sig, {"quality": 0.5}, t0)).get("reject")


def test_chop_nobias_book(tmp_path):
    """playbook_regime_nobias (Nov 4 2026): the chop/trend routing AND the bias rule off, own journal."""
    from types import SimpleNamespace

    from fxagents.agents.playbook_trader import PlaybookTrader
    from fxagents.agents.setup_first import build_shadow
    from fxagents.state import LiveState

    cfg = _cfg(modes=["playbook_regime", "playbook_regime_nobias"])
    cfg["storage"]["db_path"] = str(tmp_path / "journal.sqlite")
    from fxagents.bus import Bus
    main = SimpleNamespace(cfg=cfg, state=LiveState(), store=None, jev=None, book=None, news=None, playbook=None, bus=Bus())
    sh, agents, _ = build_shadow(main, 50_000, "playbook_regime_nobias", first=False)
    assert sh.ignore_bias is True and sh.regime_route is True
    assert any(isinstance(a, PlaybookTrader) for a in agents)
    assert str(sh.journal.path).endswith("journal_playbook_regime_nobias.sqlite")
    reg, _, _ = build_shadow(main, 50_000, "playbook_regime", first=True)
    assert reg.regime_route is True and not reg.ignore_bias
    assert sh.cfg["sessions"]["entry_windows"] == [["20:00", "23:59"], ["00:00", "15:50"]]   # all hours (Nov 4 2026)
    assert reg.cfg["sessions"]["entry_windows"] != sh.cfg["sessions"]["entry_windows"]
