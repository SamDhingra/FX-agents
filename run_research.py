"""Research grid on the cached OANDA history (data/history): every setup × variant × instrument × timeframe.

    python run_research.py                       # full grid → data/research/trades.pkl
    python run_research.py --symbols XAUUSD --tfs 5min 15min
    python run_research.py --select              # (re)build the playbook from existing trades
"""
from __future__ import annotations

import argparse
import logging
import time

from fxagents.config import load_config


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--tfs", nargs="*")
    ap.add_argument("--classes", nargs="*")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--select", action="store_true", help="only run the selection / playbook step")
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)s %(message)s", datefmt="%H:%M:%S")
    cfg = load_config(a.config)
    from fxagents import research
    t0 = time.time()
    if not a.select:
        df = research.run_all(cfg, a.symbols, a.tfs, a.classes, a.workers)
        logging.info("grid done: %d trades in %.0fs", len(df), time.time() - t0)
    try:
        from fxagents import playbook
        playbook.build(cfg)
    except ImportError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
