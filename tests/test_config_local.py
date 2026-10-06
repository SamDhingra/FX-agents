"""config.local.yaml: machine settings layered on the git config, and the one-time diff that makes it."""
import yaml

from fxagents.config import deep_merge, diff, load_config


def test_merge_and_diff_roundtrip():
    base = {"a": 1, "s": {"mode": "x", "modes": ["x", "y"], "n": 2}, "w": [[1, 2]]}
    mine = {"a": 1, "s": {"mode": "z", "modes": ["x", "y"], "n": 2, "db": "p"}, "w": [[1, 2], [3, 4]]}
    d = diff(base, mine)
    assert d == {"s": {"mode": "z", "db": "p"}, "w": [[1, 2], [3, 4]]}
    assert deep_merge(base, d) == mine
    assert deep_merge(base, {"s": {"n": 5}})["s"] == {"mode": "x", "modes": ["x", "y"], "n": 5}   # siblings kept


def test_local_file_layers_on_top(tmp_path, monkeypatch):
    monkeypatch.delenv("FX_NO_LOCAL_CONFIG", raising=False)
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"mode": "sim", "shadow": {"enabled": True, "mode": "playbook"},
                                                         "risk": {"max_open_positions": 3}}))
    (tmp_path / "config.local.yaml").write_text(yaml.safe_dump({"shadow": {"db_path": "data/j.sqlite"},
                                                               "risk": {"max_open_positions": 2}}))
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg["shadow"] == {"enabled": True, "mode": "playbook", "db_path": "data/j.sqlite"}
    assert cfg["risk"]["max_open_positions"] == 2
    monkeypatch.setenv("FX_NO_LOCAL_CONFIG", "1")
    assert load_config(tmp_path / "config.yaml")["risk"]["max_open_positions"] == 3
