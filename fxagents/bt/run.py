"""Load a plugin file and run it.  python -m fxagents.bt run btplugins/x.py --data seen [--symbol XAUUSD] [--out DIR]"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

from . import data, engine, stats
from .api import Strategy


def load_plugin(path: str | Path) -> tuple[type[Strategy], str]:
    path = Path(path)
    src = path.read_bytes()
    spec = importlib.util.spec_from_file_location(f"btplugin_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    classes = [v for v in vars(mod).values() if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy
               and v.__module__ == mod.__name__]
    if len(classes) != 1:
        raise ValueError(f"{path}: expected exactly one Strategy subclass, found {len(classes)}")
    return classes[0], hashlib.sha256(src).hexdigest()[:12]


def run(strat: Strategy, m, audit: int = 10, controls: bool = True) -> dict:
    sigs = sorted(strat.signals(m), key=lambda s: s.t)
    res = engine.simulate(strat, m, sigs, controls=controls)
    out = stats.summarize(res, m)
    out["audit"] = engine.lookahead_audit(strat, m, sigs, audit) if audit else None
    out["variants"] = {}
    for name, ov in strat.variants.items():
        v = strat.with_params(**ov)
        vo = stats.summarize(engine.simulate(v, m, controls=False), m)
        out["variants"][name] = vo["stats"]
    return {"summary": out, "trades": res["trades"]}


def _jsonable(t: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, pd.Timestamp) else v) for k, v in t.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m fxagents.bt")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("plugin")
    r.add_argument("--data", default="seen")
    r.add_argument("--symbol")
    r.add_argument("--audit", type=int, default=10)
    r.add_argument("--out", type=Path)
    r.add_argument("--set", action="append", default=[], help="param override k=v (JSON value)")
    a = ap.parse_args(argv)
    cls, sha = load_plugin(a.plugin)
    ov = {k: json.loads(v) for k, v in (x.split("=", 1) for x in a.set)}
    strat = cls(**ov)
    sym = a.symbol or strat.symbol
    if data.datasets()[a.data]["role"] == "vault":
        raise SystemExit("the vault opens through the ledger only (once, for a frozen strategy that passed on seen data)")
    m = data.load(a.data, sym)
    res = run(strat, m, a.audit)
    txt = stats.text(f"{strat.name} ({sym}, code {sha})", a.data, res["summary"], res["summary"]["audit"])
    print(txt)
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "report.md").write_text(txt)
        (a.out / "summary.json").write_text(json.dumps(res["summary"], default=str, indent=1))
        (a.out / "trades.json").write_text(json.dumps([_jsonable(t) for t in res["trades"]], default=str))


if __name__ == "__main__":
    main()
