"""Command line.  python -m fxagents.bt run btplugins/x.py [--data seen] [--symbol XAUUSD] [--set k=JSON] [--out DIR]
                  python -m fxagents.bt worker           (the fxbt container runs this)
                  python -m fxagents.bt list
Every run goes through the ledger (counted, code recorded); the vault opens only for a strategy that passed on seen data."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

from .api import Strategy


def load_plugin(path: str | Path) -> tuple[type[Strategy], str]:
    path = Path(path)
    src = path.read_bytes()
    spec = importlib.util.spec_from_file_location(f"btplugin_{hashlib.sha1(str(path).encode()).hexdigest()[:8]}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    classes = [v for v in vars(mod).values() if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy
               and v.__module__ == mod.__name__]
    if len(classes) != 1:
        raise ValueError(f"{path}: expected exactly one Strategy subclass, found {len(classes)}")
    return classes[0], hashlib.sha256(src).hexdigest()[:12]


def main(argv=None):
    from . import jobs, ledger
    ap = argparse.ArgumentParser(prog="python -m fxagents.bt")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("plugin", help="btplugins/<file>.py or just <file>.py")
    r.add_argument("--data", default="seen")
    r.add_argument("--symbol")
    r.add_argument("--audit", type=int, default=10)
    r.add_argument("--out", type=Path, help="also copy report.md / summary.json / trades.json.gz here")
    r.add_argument("--set", action="append", default=[], help="parameter override k=v (JSON value)")
    sub.add_parser("worker")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    if a.cmd == "worker":
        return jobs.worker()
    if a.cmd == "list":
        for x in ledger.runs(50):
            print(f"{x['id']}  {x['status']:9} {x['role']:5} {x['plugin']:28} {x['symbol']:7} trades {x['trades'] or 0:4}"
                  f"  avg {x['avg_r'] if x['avg_r'] is not None else float('nan'):+.3f}  pass {bool(x['passed'])}")
        return
    ov = {k: json.loads(v) for k, v in (x.split("=", 1) for x in a.set)}
    try:
        rid = ledger.enqueue(Path(a.plugin).name, a.data, a.symbol, ov, source="cli", status="running")
    except (PermissionError, ValueError) as e:
        raise SystemExit(str(e))
    jobs.execute(rid, a.audit)
    d = ledger.run_dir(rid)
    print((d / "report.md").read_text())
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        for f in ("report.md", "summary.json", "trades.json.gz", "code.py"):
            shutil.copy(d / f, a.out / f)


if __name__ == "__main__":
    main()
