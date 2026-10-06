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
