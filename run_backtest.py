"""Full-system replay backtest on cached real OANDA history.

    python run_backtest.py --days 60                    # heuristic Jev, learner on, shadow book on
    python run_backtest.py --days 60 --no-learner       # same period with the learner switched off
    python run_backtest.py --days 30 --jev live         # grade with the real Jev API (slower, uses API calls)
    python run_backtest.py --days 30 --jev live --jev-gate advisory   # Jev grades set size but never block
    python run_backtest.py --days 60 --no-trade SPX     # SPX watch-only (data, bias and map kept; no entries)
    python run_backtest.py --days 30 --shadow-mode playbook   # hourly pick vs the playbook, side by side
    ./fx.sh backtest 60 [--no-learner] [--jev live]     # on the server: separate low-priority container

Results: data/backtests/<run-id>/ (journals, report.json) and the dashboard's Backtests page.
Needs the history cache that the app's setup-map build downloads (data/history/).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

import main as app
from fxagents import backtest_report
from fxagents.config import load_config
from fxagents.replay import backtests_dir
from fxagents.setup_map import load_specs

log = logging.getLogger("backtest")


def last_live_equity(cfg) -> float | None:
    p = Path(cfg["storage"]["db_path"])
    if not p.exists():
        return None
    try:
        row = sqlite3.connect(str(p)).execute("SELECT equity FROM equity ORDER BY ts DESC LIMIT 1").fetchone()
        return float(row[0]) if row else None
    except sqlite3.Error:
        return None


def prepare(args) -> tuple[dict, Path, dict]:
    cfg = load_config(args.config)
    cfg["mode"] = "sim"
    # instrument settings as OANDA reported them (saved with the history cache)
    specs = load_specs(cfg) or {}
    for sym, ic in cfg["instruments"].items():
        o = ic.get("oanda") or {}
        for k, v in o.items():
            if k != "instrument":
                ic[k] = v
        ic.update(specs.get(sym, {}))
    from fxagents.setup_map import history_dir
    cfg["history_dir"] = str(history_dir(cfg))       # pin before the journal path moves into the run folder
    from fxagents.research import research_dir
    cfg["research_dir"] = str(research_dir(cfg))
    slug = "".join(c if c.isalnum() else "-" for c in args.name.strip().lower()).strip("-")[:30]
    rid = time.strftime("%Y%m%d-%H%M%S") + (f"-{slug}" if slug else "")
    out = backtests_dir(cfg) / rid
    out.mkdir(parents=True, exist_ok=True)
    equity = args.equity or last_live_equity(cfg) or 100000.0
    cfg["starting_equity"] = equity
    cfg["storage"]["db_path"] = str(out / "journal.sqlite")
    (cfg.setdefault("shadow", {}))["enabled"] = not args.no_shadow
    cfg["shadow"]["db_path"] = str(out / "journal_shadow.sqlite")
    cfg["shadow"]["notify_trades"] = False
    cfg["jev"]["enabled"] = args.jev == "live"
    for sym in args.no_trade or []:
        if sym not in cfg["instruments"]:
            raise SystemExit(f"--no-trade: unknown instrument {sym} (have {', '.join(cfg['instruments'])})")
        cfg["instruments"][sym]["trade"] = False
    if args.jev_gate:
        cfg["jev"]["signal_gate"] = args.jev_gate
    # the heuristic stand-in for Jev doesn't read "today's form" — skip computing it (live Jev runs keep it)
    cfg.setdefault("setup_first", {})["today_context"] = args.jev == "live"
    ev = cfg["evaluator"]
    ev["learn_enabled"] = not args.no_learner
    ev["optimize_daily"] = False                     # weekly learning keeps a 60-day replay to minutes, not hours
    ev["optimize_every_hours"] = args.learn_every_hours
    ev["refresh_minutes"] = args.refresh_minutes
    if args.main_mode:
        cfg["selector"]["mode"] = args.main_mode
    if args.shadow_mode:
        cfg["shadow"]["mode"] = args.shadow_mode
    main_mode = cfg["selector"].get("mode", "hourly_pick")
    cfg["shadow"].setdefault("mode", "hourly_pick" if main_mode != "hourly_pick" else "setup_first")
    cfg["replay"] = {"days": args.days, "dir": str(out)}
    meta = {"id": rid, "name": args.name or "", "created": pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds"),
            "days": args.days, "jev": args.jev, "jev_gate": cfg["jev"].get("signal_gate", "enforce"),
            "no_trade": [k for k, v in cfg["instruments"].items() if v.get("trade", True) is False], "learner": not args.no_learner, "shadow": not args.no_shadow,
            "equity": round(equity, 2), "main_mode": main_mode, "shadow_mode": cfg["shadow"]["mode"],
            "status": "running"}
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    return cfg, out, meta


def main() -> int:
    ap = argparse.ArgumentParser(description="FX-Agents full-system replay backtest")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--jev", choices=["heuristic", "live"], default="heuristic")
    ap.add_argument("--jev-gate", choices=["enforce", "advisory"], help="override jev.signal_gate for this run")
    ap.add_argument("--no-trade", nargs="*", metavar="SYM", help="watch-only instruments for this run, e.g. --no-trade SPX")
    ap.add_argument("--main-mode", choices=["hourly_pick", "setup_first", "playbook"], help="real book's selection mode")
    ap.add_argument("--shadow-mode", choices=["hourly_pick", "setup_first", "playbook"], help="shadow book's selection mode")
    ap.add_argument("--no-learner", action="store_true")
    ap.add_argument("--no-shadow", action="store_true")
    ap.add_argument("--equity", type=float, help="starting equity in USD (default: the live account's latest)")
    ap.add_argument("--name", default="", help="short label for the run")
    ap.add_argument("--learn-every-hours", type=float, default=168)
    ap.add_argument("--refresh-minutes", type=int, default=120, help="strategy re-ranking interval during the replay")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)-14s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cfg, out, meta = prepare(args)
    log.info("backtest %s → %s", meta["id"], out)
    ns = argparse.Namespace(config=args.config, mode=None, days=None, db=None, port=None, speed=None, broker=None,
                            no_dashboard=True, exit_after_sim=True, i_understand_live_trading=False, verbose=False)
    t0 = time.time()
    try:
        asyncio.run(app.main(ns, cfg))
        meta.update(status="done", seconds=round(time.time() - t0))
        prog = out / "progress.json"
        if prog.exists():
            p = json.loads(prog.read_text())
            meta["period"] = {"from": p.get("from"), "to": p.get("to"), "days": p.get("days")}
        rep = backtest_report.build(out, meta, cfg)
        m = rep["books"]["main"]["summary"] if rep["books"]["main"] else {}
        meta["headline"] = {k: (rep["books"][k] or {}).get("summary") for k in ("main", "shadow")}
        log.info("BACKTEST DONE in %ds: %s", meta["seconds"], m)
        (out / "meta.json").write_text(json.dumps(meta, indent=1))
        return 0
    except SystemExit as e:
        meta.update(status="failed", error=str(e))
    except Exception as e:  # noqa: BLE001
        meta.update(status="failed", error=f"{e}\n{traceback.format_exc()[-1500:]}")
        log.exception("backtest failed")
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    return 1


if __name__ == "__main__":
    sys.exit(main())
