from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class Config(dict):
    """dict with attribute access: cfg.risk.max_open_positions"""

    def __getattr__(self, k: str) -> Any:
        try:
            v = self[k]
        except KeyError as e:
            raise AttributeError(k) from e
        return Config(v) if isinstance(v, dict) and not isinstance(v, Config) else v

    def get_path(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def deep_merge(base: dict, over: dict) -> dict:
    """`over` wins; nested dicts merge key by key, anything else (lists included) is replaced whole."""
    out = dict(base)
    for k, v in (over or {}).items():
        if v is None and k in out:
            continue                    # an emptied section ("instruments:" with nothing under it) changes nothing
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def diff(base: dict, mine: dict) -> dict:
    """Only what `mine` changes relative to `base` — the minimal config.local.yaml."""
    out = {}
    for k, v in mine.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            d = diff(base[k], v)
            if d:
                out[k] = d
        elif k not in base or base[k] != v:
            out[k] = v
    return out


LOCAL_NAME = "config.local.yaml"


def load_config(path: str | Path = "config.yaml") -> Config:
    """config.yaml (from git) with config.local.yaml (this machine's settings, never committed) on top.
    FX_NO_LOCAL_CONFIG=1 skips the local file (the test suite runs on the repo defaults)."""
    path = Path(path)
    _load_dotenv(path.parent / ".env")
    raw = yaml.safe_load(path.read_text()) or {}
    local = path.parent / LOCAL_NAME
    if local.exists() and path.name == "config.yaml" and not os.environ.get("FX_NO_LOCAL_CONFIG"):
        raw = deep_merge(raw, yaml.safe_load(local.read_text()) or {})
    # an instrument only named in config.local.yaml (e.g. one removed from config.yaml) has no contract spec
    for sym in [s for s, ic in (raw.get("instruments") or {}).items() if not isinstance(ic, dict) or "multiplier" not in ic]:
        import logging
        logging.getLogger("config").warning("instrument %s ignored: not in config.yaml (remove it from %s)", sym, LOCAL_NAME)
        raw["instruments"].pop(sym)
    cfg = Config(raw)
    # secrets from the environment win over the file
    env_map = {
        "notifications.telegram_bot_token": "TELEGRAM_BOT_TOKEN",
        "notifications.telegram_chat_id": "TELEGRAM_CHAT_ID",
        "notifications.ntfy_topic": "NTFY_TOPIC",
        "dashboard.token": "DASHBOARD_TOKEN",
        "tradingview.webhook_secret": "TV_WEBHOOK_SECRET",
        "mode": "FX_MODE",
        "broker": "FX_BROKER",
        "oanda.environment": "OANDA_ENVIRONMENT",
        # cloud / container overrides
        "ibkr.host": "IB_HOST",
        "ibkr.port": "IB_PORT",
        "ibkr.client_id": "IB_CLIENT_ID",
        "ibkr.account": "IB_ACCOUNT",
        "dashboard.port": "DASHBOARD_PORT",
        "storage.db_path": "FX_DB_PATH",
    }
    for dotted, env in env_map.items():
        if os.environ.get(env):
            *parents, leaf = dotted.split(".")
            node = cfg
            for p in parents:
                node = node.setdefault(p, {})
            node[leaf] = os.environ[env]
    return cfg


def apply_broker(cfg: Config) -> Config:
    """For paper/live on OANDA, swap each instrument's IBKR futures spec for its `oanda:` block.
    Sim and backtests keep the top-level values. Idempotent."""
    cfg.setdefault("broker", "ibkr")
    if cfg["broker"] not in ("ibkr", "oanda"):
        raise SystemExit(f"broker must be ibkr or oanda, not {cfg['broker']!r}")
    if cfg["mode"] == "sim" or cfg["broker"] != "oanda" or cfg.get("_broker_applied"):
        return cfg
    for sym, ic in cfg["instruments"].items():
        o = ic.get("oanda")
        if not o or not o.get("instrument"):
            raise SystemExit(f"{sym}: broker is oanda but instruments.{sym}.oanda.instrument is not set")
        ic["oanda_instrument"] = o["instrument"]
        for k, v in o.items():
            if k != "instrument":
                ic[k] = v
    cfg["_broker_applied"] = True
    return cfg


if __name__ == "__main__":
    # python -m fxagents.config diff OLD_FULL_CONFIG.yaml  →  prints the minimal config.local.yaml
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != "diff":
        sys.exit("usage: python -m fxagents.config diff <your full config.yaml copy>")
    base = yaml.safe_load(Path("config.yaml").read_text()) or {}
    mine = yaml.safe_load(Path(sys.argv[2]).read_text()) or {}
    d = diff(base, mine)
    print("# This machine's settings on top of config.yaml (git). Not committed — edit freely.")
    print(yaml.safe_dump(d, sort_keys=False, default_flow_style=None, width=120) if d else "{}")
