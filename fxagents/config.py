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


def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path)
    _load_dotenv(path.parent / ".env")
    cfg = Config(yaml.safe_load(path.read_text()))
    # secrets from the environment win over the file
    env_map = {
        "notifications.telegram_bot_token": "TELEGRAM_BOT_TOKEN",
        "notifications.telegram_chat_id": "TELEGRAM_CHAT_ID",
        "notifications.ntfy_topic": "NTFY_TOPIC",
        "dashboard.token": "DASHBOARD_TOKEN",
        "tradingview.webhook_secret": "TV_WEBHOOK_SECRET",
        "mode": "FX_MODE",
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
