"""The protocol ledger: every backtest run is recorded (exact code, parameters, data, result), tries are counted, and
the untouched vault data opens only for the IDENTICAL strategy (same code sha, same parameters, same symbol) that
passed every gate on seen data — once.

Runs live in data/bt/ledger.sqlite; each run's files (the code that ran, summary, trades, report) in data/bt/runs/<id>/.
Plugins are the .py files in btplugins/ (delivered by git — never uploaded through the web)."""
from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path

from .data import ROOT, datasets
from .run import code_sha

PLUGINS = Path("btplugins")
SCHEMA = """CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, created REAL, plugin TEXT, name TEXT, code_sha TEXT, params TEXT, symbol TEXT, dataset TEXT,
  role TEXT, status TEXT, stage TEXT, pct REAL, started REAL, finished REAL, trades INTEGER, avg_r REAL, ci_lo REAL,
  passed INTEGER, error TEXT, source TEXT, note TEXT)"""
LIVE = ("queued", "running", "done")


def db() -> sqlite3.Connection:
    ROOT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ROOT / "ledger.sqlite", timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(SCHEMA)
    return con


def run_dir(rid: str) -> Path:
    return ROOT / "runs" / rid


def canon(params: dict) -> str:
    return json.dumps(params, sort_keys=True, default=list, separators=(",", ":"))


# ── plugin catalog (read with ast — nothing is executed to list them) ──
def _class_info(src: str) -> dict | None:
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and any(getattr(b, "id", getattr(b, "attr", "")) in ("Strategy", "BotSetup")
                                                  for b in node.bases):
            info = {"class": node.name, "name": node.name, "symbol": "XAUUSD", "description": "", "params": {},
                    "variants": {}, "doc": ast.get_docstring(tree) or ""}
            for st in node.body:
                if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
                    k = st.targets[0].id
                    if k in ("name", "symbol", "description", "params", "variants"):
                        try:
                            info[k] = ast.literal_eval(st.value)
                        except ValueError:
                            pass
            return info
    return None


def plugins() -> list[dict]:
    out = []
    for f in sorted(PLUGINS.glob("*.py")):
        if f.name.startswith("_"):
            continue
        src = f.read_bytes()
        try:
            info = _class_info(src.decode())
        except SyntaxError as e:
            out.append({"file": f.name, "error": f"syntax error line {e.lineno}"})
            continue
        if info:
            out.append({"file": f.name, "code_sha": code_sha(src), **info})
    return out


def plugin(file: str) -> dict:
    if "/" in file or not file.endswith(".py"):
        raise ValueError("plugin must be a file name in btplugins/")
    for p in plugins():
        if p["file"] == file:
            if "error" in p:
                raise ValueError(f"{file}: {p['error']}")
            return p
    raise ValueError(f"no plugin {file} in btplugins/")


def merged_params(p: dict, overrides: dict | None) -> dict:
    ov = overrides or {}
    bad = [k for k in ov if k not in p["params"]]
    if bad:
        raise ValueError(f"unknown parameter(s): {', '.join(bad)}")
    return json.loads(canon({**p["params"], **ov}))


# ── the protocol ──
def vault_check(con, file: str, code_sha: str, params: str, symbol: str) -> tuple[bool, str]:
    seen = con.execute("SELECT id, passed FROM runs WHERE plugin=? AND code_sha=? AND params=? AND symbol=? AND role='seen'"
                       " AND status='done' ORDER BY created DESC", (file, code_sha, params, symbol)).fetchall()
    if not any(r["passed"] for r in seen):
        return False, ("this exact code + parameters has not passed on seen data" if seen else
                       "no finished seen-data run of this exact code + parameters")
    opened = con.execute(f"SELECT id FROM runs WHERE plugin=? AND code_sha=? AND params=? AND symbol=? AND role='vault'"
                         f" AND status IN {LIVE}", (file, code_sha, params, symbol)).fetchone()
    if opened:
        return False, f"the vault was already opened for it (run {opened['id']})"
    return True, "passed on seen data — the vault can be opened once"


def tries(con, file: str) -> dict:
    rows = con.execute("SELECT role, COUNT(*) n FROM runs WHERE plugin=? AND status='done' GROUP BY role", (file,))
    return {r["role"]: r["n"] for r in rows}


def enqueue(file: str, dataset: str, symbol: str | None = None, overrides: dict | None = None, source: str = "app",
            note: str = "", status: str = "queued") -> str:
    p = plugin(file)
    ds = datasets()
    if dataset not in ds:
        raise ValueError(f"unknown dataset {dataset!r}")
    role = ds[dataset]["role"]
    symbol = symbol or p["symbol"]
    params = canon(merged_params(p, overrides))
    con = db()
    try:
        con.execute("BEGIN IMMEDIATE")
        if role == "vault":
            ok, why = vault_check(con, file, p["code_sha"], params, symbol)
            if not ok:
                raise PermissionError(f"vault refused: {why}")
        rid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        d = run_dir(rid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "code.py").write_bytes((PLUGINS / file).read_bytes())          # the exact code that will run
        con.execute("INSERT INTO runs (id, created, plugin, name, code_sha, params, symbol, dataset, role, status, stage,"
                    " pct, source, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
                    (rid, time.time(), file, p["name"], p["code_sha"], params, symbol, dataset, role, status, status,
                     source, note[:200]))
        con.execute("COMMIT")
        return rid
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def get(rid: str) -> dict | None:
    con = db()
    try:
        r = con.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def update(rid: str, **kw):
    con = db()
    try:
        con.execute(f"UPDATE runs SET {', '.join(f'{k}=?' for k in kw)} WHERE id=?", (*kw.values(), rid))
    finally:
        con.close()


def claim() -> dict | None:
    con = db()
    try:
        con.execute("BEGIN IMMEDIATE")
        r = con.execute("SELECT * FROM runs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
        if r:
            con.execute("UPDATE runs SET status='running', stage='starting', started=? WHERE id=?", (time.time(), r["id"]))
        con.execute("COMMIT")
        return dict(r) if r else None
    finally:
        con.close()


def runs(limit: int = 100) -> list[dict]:
    con = db()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM runs ORDER BY created DESC LIMIT ?", (limit,))]
    finally:
        con.close()


def catalog() -> dict:
    """Everything the app's Backtest page lists: plugins (with tries and vault eligibility), datasets, recent runs."""
    from .data import symbols
    con = db()
    try:
        ps = plugins()
        for p in ps:
            if "error" in p:
                continue
            p["tries"] = tries(con, p["file"])
            ok, why = vault_check(con, p["file"], p["code_sha"], canon(p["params"]), p["symbol"])
            p["vault"] = {"eligible": ok, "why": why}
        dss = []
        for k, v in datasets().items():
            try:
                syms = symbols(k)
            except OSError:
                syms = []
            dss.append({"name": k, "role": v["role"], "label": v.get("label", k), "symbols": syms})
        return {"plugins": ps, "datasets": dss, "runs": [dict(r) for r in con.execute(
            "SELECT * FROM runs ORDER BY created DESC LIMIT 100")]}
    finally:
        con.close()
