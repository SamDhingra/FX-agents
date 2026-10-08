"""Playbook strategy: research → selection → walk-forward validation → live playbook.

A *cell* is one setup variant on one instrument, timeframe and exit profile (std / scalp). The
playbook is the set of cells the policy currently allows, re-selected every week from the trailing
`window_days` of history, exactly as validated here:

  • per-instrument rules — XAUUSD is the core instrument (more cells, more concurrent positions, a lower
    bar); NDQ / US30 only trade cells whose estimated win probability is ≥ 50%
  • a cell's win probability and expectancy are SHRUNK toward its instrument/timeframe pool
    (Bayesian, `k` pseudo-trades), because raw stats over a few dozen trades mostly measure luck
  • a cell must have been positive in both halves of the window (stability), with enough trades
  • at most `max_cells` per instrument (best shrunk expectancy first), one variant per setup/TF/exit

`walk_forward()` replays that weekly re-selection over history and measures only weeks the selection
had not seen. `portfolio()` then applies the live capacity rules (per-instrument caps, the index
group cap, max open positions, the daily loss limit) to that trade stream.
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("playbook")

KEY = ["sym", "tf", "setup", "variant", "mgmt"]
TF_MIN = {"1min": 1, "3min": 3, "5min": 5, "15min": 15, "30min": 30, "1h": 60}


@dataclass
class InstrumentRule:
    role: str = "selective"          # core | selective | off
    min_p: float = 0.60              # shrunk win probability needed
    min_e: float = 0.03              # shrunk expectancy (R, after spread) needed
    max_cells: int = 6
    max_positions: int = 1
    k_p: float | None = None         # instrument-specific shrinkage (None = policy default)
    min_n: int | None = None         # instrument-specific minimum trades (None = policy default)


@dataclass
class Policy:
    name: str = "default"
    window_days: int = 60
    min_n: int = 25
    k_p: float = 20.0                # pseudo-trades pulling win rate toward the pool's
    k_e: float = 30.0                # pseudo-trades pulling expectancy toward min(pool, 0)
    halves_positive: bool = True
    # 1-minute cells are excluded: the spread is 13–30% of a 1m bar, and in walk-forward they hurt
    tfs: tuple = ("3min", "5min", "15min", "30min", "1h")
    instruments: dict = field(default_factory=lambda: {
        "XAUUSD": InstrumentRule("core", 0.45, 0.02, 10, 2),
        # indices: 50% bar (was 60% until Oct 2026 — nothing cleared it), still with heavier shrinkage and
        # more trades before an estimate is believed (estimates of 0.60–0.65 realised ~0.45 in walk-forward)
        "NDQ": InstrumentRule("selective", 0.50, 0.03, 4, 1, k_p=40.0, min_n=30),
        "US30": InstrumentRule("selective", 0.50, 0.03, 4, 1, k_p=40.0, min_n=30),
        # forex majors: gold-like selection, one position each (they all move with the dollar → max_open caps the total)
        "EURUSD": InstrumentRule("core", 0.50, 0.02, 4, 1),
        "GBPUSD": InstrumentRule("core", 0.50, 0.02, 4, 1),
        "AUDUSD": InstrumentRule("core", 0.50, 0.02, 4, 1)})
    index_group: tuple = ("NDQ", "US30")
    index_group_max: int = 1          # NDQ / US30 move together: one index position at a time
    max_open: int = 3
    daily_loss_r: float = 4.0         # -2% day at 0.5% per trade = -4R
    # volume cells (vol=impulse/dry/climax variants, the VWAP setup) are researched and shown, but only
    # traded when this is on: in the first walk-forward they lost (22 trades, -2.4R vs +3.5R for the rest)
    volume: bool = False

    def to_json(self) -> dict:
        d = asdict(self)
        d["tfs"] = list(self.tfs)
        d["index_group"] = list(self.index_group)
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Policy":
        d = deepcopy(d)
        d["instruments"] = {k: InstrumentRule(**v) for k, v in d.get("instruments", {}).items()}
        d["tfs"] = tuple(d.get("tfs", cls.tfs))
        d["index_group"] = tuple(d.get("index_group", cls.index_group))
        return cls(**d)


# ── cell statistics over a window (vectorised via per-day cumulative sums) ───
class CellCube:
    """Per-cell, per-day cumulative sums. Expectancy is measured on `val` — `rw` (R weighted by the size
    Risk can really take, in units of the full budget) when the research has it, else plain `r`.
    Statistics use each cell's own one-at-a-time record (busy_self rows dropped); `self.trades` keeps every
    candidate so the walk-forward → portfolio replay applies occupancy only to the positions it accepted.
    A trade counts toward a selection made at day b's start only if it had EXITED by then (window())."""

    def __init__(self, trades: pd.DataFrame, val: str | None = None) -> None:
        t = trades.copy()
        self.val = val or ("rw" if "rw" in t.columns else "r")
        t["win"] = (t["r"] > 0).astype(float)
        t["_v"] = t[self.val]
        self.days = sorted(t["day"].unique())
        self.day_ix = {d: i for i, d in enumerate(self.days)}
        t["di"] = t["day"].map(self.day_ix)
        cells = t[KEY].drop_duplicates().reset_index(drop=True)
        cells["ci"] = np.arange(len(cells))
        t = t.merge(cells, on=KEY)
        self.cells, self.trades = cells, t
        own = ~t["busy_self"].astype(bool) if "busy_self" in t.columns else pd.Series(True, index=t.index)
        C, D = len(cells), len(self.days)
        self.n = np.zeros((C, D + 1)); self.w = np.zeros((C, D + 1)); self.s = np.zeros((C, D + 1))
        g = t[own].groupby(["ci", "di"]).agg(n=("r", "size"), w=("win", "sum"), s=("_v", "sum"))
        ci, di = g.index.get_level_values(0), g.index.get_level_values(1)
        self.n[ci, di + 1] = g["n"]; self.w[ci, di + 1] = g["w"]; self.s[ci, di + 1] = g["s"]
        self.n, self.w, self.s = (np.cumsum(x, axis=1) for x in (self.n, self.w, self.s))
        self.pool = cells[["sym", "tf", "mgmt"]].astype(str).agg("|".join, axis=1).to_numpy()
        # sums are by ENTRY day; the few trades that exit on a later trading day (gaps, long holds) are kept
        # aside so window() can take them out again when their exit is at/after the selection cutoff (F24)
        self.cross = None
        if "exit_ts" in t.columns:
            xday = pd.to_datetime((pd.to_datetime(t["exit_ts"]) + pd.Timedelta(hours=7)).dt.date)
            c = (own & (xday > pd.to_datetime(t["day"]))).to_numpy()
            self.cross = t.loc[c, ["ci", "di", "win", "_v"]].assign(xday=xday[c])

    def window(self, a: int, b: int, cutoff=None) -> pd.DataFrame:
        """Stats of every cell over trading days [a, b), counting only trades whose exit's trading day is
        before `cutoff` (default: day b — a selection made as day b starts)."""
        a, b = max(0, a), max(0, b)
        n, w, s = (x[:, b] - x[:, a] for x in (self.n, self.w, self.s))
        m = (a + b) // 2
        n1, s1 = self.n[:, m] - self.n[:, a], self.s[:, m] - self.s[:, a]
        cutoff = cutoff if cutoff is not None else (self.days[b] if b < len(self.days) else None)
        if cutoff is not None and self.cross is not None and len(self.cross):
            x = self.cross
            x = x[(x["di"] >= a) & (x["di"] < b) & (x["xday"] >= pd.Timestamp(cutoff))]
            if len(x):                                  # entered inside the window, outcome not known yet
                C, ci, f = len(self.cells), x["ci"].to_numpy(), (x["di"] < m).to_numpy()
                bc = lambda k, v=None: np.bincount(k, weights=v, minlength=C)  # noqa: E731
                n, w, s = n - bc(ci), w - bc(ci, x["win"].to_numpy()), s - bc(ci, x["_v"].to_numpy())
                n1, s1 = n1 - bc(ci[f]), s1 - bc(ci[f], x["_v"].to_numpy()[f])
        n2, s2 = n - n1, s - s1
        out = self.cells.copy()
        out["n"], out["wins"], out["sum_r"] = n, w, s
        out["exp1"] = np.where(n1 > 0, s1 / np.maximum(n1, 1), np.nan)
        out["exp2"] = np.where(n2 > 0, s2 / np.maximum(n2, 1), np.nan)
        out["pool"] = self.pool
        pg = out.groupby("pool")[["n", "wins", "sum_r"]].transform("sum")
        out["p0"] = np.where(pg["n"] > 0, pg["wins"] / np.maximum(pg["n"], 1), 0.45)
        out["e0"] = np.where(pg["n"] > 0, pg["sum_r"] / np.maximum(pg["n"], 1), 0.0)
        return out


def _rule(pol: Policy, sym: str) -> InstrumentRule:
    return pol.instruments.get(sym) or InstrumentRule("off", 1.0, 9.0, 0, 0)


def score(st: pd.DataFrame, pol: Policy) -> pd.DataFrame:
    st = st.copy()
    kp = st["sym"].map(lambda s: _rule(pol, s).k_p if _rule(pol, s).k_p is not None else pol.k_p).astype(float)
    st["p"] = (st["wins"] + kp * st["p0"]) / (st["n"] + kp)
    st["e"] = (st["sum_r"] + pol.k_e * np.minimum(st["e0"], 0)) / (st["n"] + pol.k_e)
    st["raw_wr"] = np.where(st["n"] > 0, st["wins"] / np.maximum(st["n"], 1), np.nan)
    st["raw_e"] = np.where(st["n"] > 0, st["sum_r"] / np.maximum(st["n"], 1), np.nan)
    return st


def eligible(st: pd.DataFrame, pol: Policy) -> pd.Series:
    """Which scored cells pass the policy (before the per-instrument cap)."""
    min_n = st["sym"].map(lambda s: _rule(pol, s).min_n if _rule(pol, s).min_n is not None else pol.min_n)
    ok = (st["n"] >= min_n) & st["tf"].isin(pol.tfs)
    if not pol.volume:
        ok &= ~(st["variant"].astype(str).str.contains("vol=") | (st["setup"] == "vwap"))
    if pol.halves_positive:
        ok &= (st["exp1"] > 0) & (st["exp2"] > 0)
    rules = st["sym"].map(lambda s: _rule(pol, s))
    ok &= np.array([r.role != "off" and p >= r.min_p and e >= r.min_e
                    for r, p, e in zip(rules, st["p"], st["e"])], bool)
    return ok


def select(st: pd.DataFrame, pol: Policy) -> pd.DataFrame:
    st = score(st, pol)
    x = st[eligible(st, pol)].sort_values("e", ascending=False)
    x = x.drop_duplicates(["sym", "tf", "setup", "mgmt"])
    caps = {s: r.max_cells for s, r in pol.instruments.items()}
    parts = [g.head(caps.get(sym, 0)) for sym, g in x.groupby("sym")]
    return pd.concat(parts) if parts else x.iloc[:0]


def walk_forward(trades: pd.DataFrame, pol: Policy, start_day=None, cube: CellCube | None = None) -> pd.DataFrame:
    """Weekly re-selection on the trailing window; returns the trades the selection would then have
    taken in the following (unseen) week, before portfolio capacity rules. The window is counted in
    OBSERVED TRADE DAYS (cube.days = days with ≥1 research trade in any cell), not calendar days; the
    first weeks after `start_day` select on fewer days than window_days. Every candidate of a selected
    cell is returned (incl. busy_self rows): portfolio() decides occupancy from what it accepted."""
    cube = cube or CellCube(trades)
    days = cube.days
    t = cube.trades
    week = pd.to_datetime(pd.Series(days)).dt.to_period("W-SUN").to_numpy()
    start_ix = cube.day_ix.get(start_day, 20) if start_day is not None else 20
    out = []
    i = start_ix
    while i < len(days):
        j = i
        while j < len(days) and week[j] == week[i]:
            j += 1
        sel = select(cube.window(i - pol.window_days, i), pol)
        if len(sel):
            x = t[(t["di"] >= i) & (t["di"] < j) & t["ci"].isin(sel["ci"])]
            x = x.merge(sel[["ci", "p", "e", "n"]].rename(columns={"n": "n_train"}), on="ci")
            x["week"] = str(days[i])
            out.append(x)
        i = j
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=list(t.columns) + ["p", "e"])


def portfolio(taken: pd.DataFrame, pol: Policy) -> pd.DataFrame:
    """Apply live capacity: per-instrument caps, the index group cap, max open, one entry per
    instrument/timeframe bar, no opposite positions on one instrument (OANDA refuses those), and the
    daily loss stop — counted on trades already CLOSED when the next one would open.
    Higher estimated win probability wins a tie on the same bar."""
    if not len(taken):
        return taken
    t = taken.copy()
    val = "rw" if "rw" in t.columns else "r"
    if "exit_ts" not in t.columns:
        t["exit_ts"] = t["ts"] + pd.to_timedelta(t["bars"] * t["tf"].map(TF_MIN), unit="min")
    t = t.sort_values(["ts", "p"], ascending=[True, False]).reset_index(drop=True)
    open_: list[tuple] = []           # (exit_ts, sym, cell, side, day, value)
    day_closed: dict = {}
    seen_bar: set = set()
    keep = np.zeros(len(t), bool)
    for k, r in enumerate(t.itertuples(index=False)):
        still = []
        for o in open_:
            if o[0] <= r.ts:
                day_closed[o[4]] = day_closed.get(o[4], 0.0) + o[5]
            else:
                still.append(o)
        open_ = still
        if day_closed.get(r.day, 0.0) <= -pol.daily_loss_r:
            continue
        rule = pol.instruments.get(r.sym)
        if rule is None or rule.role == "off":
            continue
        if (r.sym, r.tf, r.ts) in seen_bar:
            continue
        if len(open_) >= pol.max_open or sum(o[1] == r.sym for o in open_) >= rule.max_positions:
            continue
        if any(o[2] == (r.sym, r.tf, r.setup, r.mgmt) for o in open_):
            continue
        if any(o[1] == r.sym and o[3] != r.side for o in open_):
            continue
        if r.sym in pol.index_group and sum(o[1] in pol.index_group for o in open_) >= pol.index_group_max:
            continue
        keep[k] = True
        seen_bar.add((r.sym, r.tf, r.ts))
        open_.append((r.exit_ts, r.sym, (r.sym, r.tf, r.setup, r.mgmt), r.side, r.day, getattr(r, val)))
    return t[keep].reset_index(drop=True)


def day_block_ci(vals, days, n_boot: int = 2000, seed: int = 7) -> dict | None:
    """95% interval of the average R per trade from a DAY-BLOCK bootstrap: whole trading days are resampled
    (trades on one day share the market and move together), not single trades. `share_le0` = share of the
    resampled averages ≤ 0 — a tail fraction of this bootstrap, NOT the probability that the true edge is
    ≤ 0, and nothing here corrects for how the strategy was selected (multiple testing)."""
    g = pd.DataFrame({"v": np.asarray(vals, float), "d": list(days)}).groupby("d")["v"].agg(["sum", "size"])
    if len(g) < 2:
        return None
    k = np.random.default_rng(seed).integers(0, len(g), size=(n_boot, len(g)))
    means = g["sum"].to_numpy()[k].sum(axis=1) / g["size"].to_numpy()[k].sum(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {"lo": round(float(lo), 4), "hi": round(float(hi), 4), "share_le0": round(float((means <= 0).mean()), 3),
            "days": int(len(g))}


def days_of(x: pd.DataFrame):
    """Trading day (17:00 → 17:00 NY) of each trade: the `day` column, else derived from `ts`."""
    return x["day"] if "day" in x.columns else (pd.to_datetime(x["ts"]) + pd.Timedelta(hours=7)).dt.date


def summarize(x: pd.DataFrame, col: str | None = None) -> dict:
    """Headline stats on `col` (default: budget-weighted `rw` when present; named in `units`).
    `sum_r_unweighted` is the same trades in plain R (each trade's own risk), for reference.
    `avg_ci95` = day-block bootstrap 95% interval of the average per trade. `p_boot` (kept for the dashboard)
    is that bootstrap's share of averages ≤ 0 — a tail fraction, not "the chance the edge is ≤ 0"."""
    if not len(x):
        return {"trades": 0, "win_rate": 0.0, "avg_r": 0.0, "sum_r": 0.0, "max_dd_r": 0.0, "pf": None,
                "sum_r_unweighted": 0.0, "t_stat": None, "p_boot": None, "avg_ci95": None, "units": col,
                "top1_share": None, "sum_ex_top3": None}
    col = col or ("rw" if "rw" in x.columns else "r")
    y = x.sort_values("ts")
    r = y[col].to_numpy(dtype=float)
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min())
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    sd = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    t_stat = float(r.mean() / (sd / np.sqrt(len(r)))) if sd > 0 else None
    ci = day_block_ci(r, days_of(y))
    srt = np.sort(r)[::-1]
    return {"trades": int(len(r)), "win_rate": round(float((y["r"] > 0).mean()), 3), "avg_r": round(float(r.mean()), 3),
            "sum_r": round(float(r.sum()), 2), "max_dd_r": round(dd, 2),
            "pf": round(float(wins / losses), 2) if losses > 0 else None,
            "sum_r_unweighted": round(float(y["r"].sum()), 2),
            "t_stat": round(t_stat, 2) if t_stat is not None else None,
            "p_boot": ci["share_le0"] if ci else None,
            "avg_ci95": [ci["lo"], ci["hi"]] if ci else None, "ci_days": ci["days"] if ci else None,
            "ci_method": "day-block bootstrap (trading days resampled), 95% interval of avg per trade", "units": col,
            "top1_share": round(float(srt[0] / r.sum()), 2) if r.sum() > 0 else None,
            "sum_ex_top3": round(float(srt[3:].sum()), 2) if len(r) > 3 else None}


# ── policy from config, cells → live specs ────────────────────────────────────
def policy_from_cfg(cfg) -> Policy:
    pc = (cfg.get("playbook") or {})
    pol = Policy()
    for k in ("window_days", "min_n", "k_p", "k_e", "halves_positive", "max_open", "daily_loss_r", "index_group_max",
              "volume"):
        if k in pc:
            setattr(pol, k, pc[k])
    if "tfs" in pc:
        pol.tfs = tuple(str(t) for t in pc["tfs"])
    for sym, over in (pc.get("instruments") or {}).items():
        base = asdict(pol.instruments.get(sym, InstrumentRule()))
        pol.instruments[sym] = InstrumentRule(**{**base, **over})
    # an instrument switched to watch-only in the config never trades from the playbook either
    for sym, ic in cfg["instruments"].items():
        if ic.get("trade", True) is False:
            pol.instruments[sym] = InstrumentRule("off", 1.0, 9.0, 0, 0)
    for sym in list(pol.instruments):
        if sym not in cfg["instruments"]:
            pol.instruments.pop(sym)
    return pol


def params_of(setup: str, variant: str) -> dict:
    """'default' / 'k=v,k2=v2' → the parameter change, with its real types (from the variant list)."""
    from .research import variants, vkey
    from .strategies import ALL
    for ch in variants(ALL[setup]):
        if vkey(ch) == variant:
            return ch
    raise KeyError(f"{setup}: unknown variant {variant}")


SYM_TAG = {"XAUUSD": "xau", "NDQ": "ndq", "US30": "us30", "SPX": "spx", "EURUSD": "eu", "GBPUSD": "gu", "AUDUSD": "au"}


def cell_id(setup: str, tf: str, variant: str, mgmt: str, sym: str = "") -> str:
    import hashlib
    tag = "d" if variant == "default" else hashlib.sha1(variant.encode()).hexdigest()[:4]
    st = SYM_TAG.get(sym, sym.lower()[:4])
    return f"{setup}:{TF_MIN[tf]}m@pb{'-' + st if st else ''}-{tag}{'-' + mgmt if mgmt in ('scalp', 'trend') or mgmt.startswith('tp') else ''}"


def cells_json(sel: pd.DataFrame) -> list[dict]:
    out = []
    for r in sel.itertuples(index=False):
        try:
            params = params_of(r.setup, r.variant)
        except KeyError as e:                     # a setup's grid changed since the research ran
            log.warning("playbook: skipping %s/%s (%s)", r.setup, r.variant, e)
            continue
        out.append({"id": cell_id(r.setup, r.tf, r.variant, r.mgmt, r.sym), "sym": r.sym, "tf": r.tf, "setup": r.setup,
                    "variant": r.variant, "params": params, "mgmt": r.mgmt,
                    "n": int(r.n), "win_rate": round(float(r.raw_wr), 3), "p": round(float(r.p), 3),
                    "exp_r": round(float(r.raw_e), 3), "e": round(float(r.e), 3),
                    "exp_first_half": round(float(r.exp1), 3), "exp_second_half": round(float(r.exp2), 3)})
    return out


# ── as-of selection (live and replays: only days strictly before `day`) ──────
_CUBE: dict = {}


def trades_path(cfg) -> Path:
    from .research import research_dir
    return research_dir(cfg) / "trades.pkl"


def load_cube(cfg) -> CellCube | None:
    p = trades_path(cfg)
    if not p.exists():
        return None
    key = (str(p), p.stat().st_mtime)
    if _CUBE.get("key") != key:
        _CUBE.clear()
        _CUBE.update(key=key, cube=CellCube(pd.read_pickle(p)))
    return _CUBE["cube"]


def select_asof(cfg, day, pol: Policy | None = None) -> dict:
    """The playbook as it would have been chosen at the start of `day` (a date)."""
    pol = pol or policy_from_cfg(cfg)
    cube = load_cube(cfg)
    if cube is None:
        return {"cells": [], "asof": str(day), "why": "no research trades yet"}
    b = int(np.searchsorted(np.array(cube.days), day))
    sel = select(cube.window(b - pol.window_days, b, cutoff=day), pol)
    return {"asof": str(day), "window": [str(cube.days[max(0, b - pol.window_days)]) if b else None,
                                         str(cube.days[b - 1]) if b else None],
            "cells": cells_json(sel), "policy": pol.to_json()}


def pinned_cells(cfg) -> list[dict]:
    """`playbook.pinned`: cells traded every week whether or not the weekly selection picks them
    (a setup you've decided to run on its measured record). Same shape as selected cells."""
    out = []
    for c in ((cfg.get("playbook") or {}).get("pinned") or []):
        try:
            sym, tf, setup = c["sym"], c["tf"], c["setup"]
            from .strategies import ALL
            base = ALL[setup].default_params
            params = {k: v for k, v in (c.get("params") or {}).items() if base.get(k) != v}   # same id as research's
            variant = ",".join(f"{k}={v}" for k, v in sorted(params.items())) or "default"
            mgmt = c.get("mgmt", "std")
            out.append({"id": cell_id(setup, tf, variant, mgmt, sym), "sym": sym, "tf": tf, "setup": setup,
                        "variant": variant, "params": params, "mgmt": mgmt, "pinned": True,
                        "n": int(c.get("n", 0)), "win_rate": float(c.get("win_rate", 0.5)),
                        "p": float(c.get("p", c.get("win_rate", 0.5))), "exp_r": float(c.get("exp_r", 0.0)),
                        "e": float(c.get("exp_r", 0.0)), **({"lab_id": c["lab_id"]} if c.get("lab_id") else {})})
        except (KeyError, TypeError, ValueError) as e:
            log.warning("playbook.pinned entry %r skipped: %s", c, e)
    return out


def pin_active(pin: dict, asof=None, tz: str = "America/New_York") -> bool:
    """A pin applies only from its `effective_from` (the promotion time) on — a replay or walk-forward
    before that date must not trade it (F18). `asof`: a timestamp (the clock), or a trading-day date (which
    starts 17:00 NY the evening before); None = now. Pins without effective_from (config pins) always apply."""
    ef = pin.get("effective_from")
    if not ef:
        return True
    ef = pd.Timestamp(ef)
    ef = ef if ef.tzinfo else ef.tz_localize(tz)
    if asof is None:
        at = pd.Timestamp.now(tz=tz)
    elif isinstance(asof, pd.Timestamp) or (isinstance(asof, str) and len(asof) > 10):
        at = pd.Timestamp(asof)
        at = at if at.tzinfo else at.tz_localize(tz)
    else:                                                # a trading day: it starts at 17:00 NY the day before
        at = pd.Timestamp(str(asof)).tz_localize(tz) - pd.Timedelta(hours=7)
    return bool(ef <= at)


def with_pinned(cfg, data: dict, asof=None) -> dict:
    """Selected cells + config pins + cells promoted from the strategy lab (data/lab/pinned.json), each
    only from its effective_from on (asof: the clock or trading day this playbook is for; None = now)."""
    have = {c["id"] for c in data.get("cells", [])}
    try:
        from .lab import lab_pinned
        lab = [p for p in lab_pinned(cfg) if pin_active(p, asof, cfg.get("timezone", "America/New_York"))]
    except Exception:  # noqa: BLE001
        lab = []
    conf = [p for p in ((cfg.get("playbook") or {}).get("pinned") or [])
            if pin_active(p, asof, cfg.get("timezone", "America/New_York"))]
    extra = []
    for c in pinned_cells({"playbook": {"pinned": conf}}) + pinned_cells({"playbook": {"pinned": lab}}):
        if c["id"] not in have:
            have.add(c["id"])
            extra.append(c)
    return {**data, "cells": list(data.get("cells", [])) + extra} if extra else data


def playbook_path(cfg) -> Path:
    return Path(cfg["storage"]["db_path"]).parent / "playbook.json"


# ── build: validation + current playbook + dashboard summary ─────────────────
def _heat(t: pd.DataFrame, oos_from) -> list[dict]:
    """Per instrument × setup × timeframe × exit profile: the best variant's stats (all / in / out of sample)."""
    v = "rw" if "rw" in t.columns else "r"
    t = t.assign(win=t["r"] > 0, oos=t["day"] >= oos_from, mo=pd.to_datetime(t["day"]).dt.strftime("%Y-%m"), _v=t[v],
                 _w=t["w"] if "w" in t.columns else 1.0)
    g = t.groupby(KEY).agg(n=("r", "size"), wr=("win", "mean"), exp=("_v", "mean"), exp_unw=("r", "mean"),
                           size=("_w", "mean"), cost=("cost_r", "mean"))
    gi = t[~t["oos"]].groupby(KEY).agg(n_is=("r", "size"), exp_is=("_v", "mean"), wr_is=("win", "mean"))
    go = t[t["oos"]].groupby(KEY).agg(n_oos=("r", "size"), exp_oos=("_v", "mean"), wr_oos=("win", "mean"))
    mo = t.groupby(KEY + ["mo"])["_v"].mean().unstack("mo")
    g = g.join(gi).join(go)
    g["months_pos"] = (mo > 0).sum(axis=1).reindex(g.index)
    g["months"] = mo.notna().sum(axis=1).reindex(g.index)
    g = g[g["n"] >= 10].reset_index()
    g = g.sort_values("exp", ascending=False).drop_duplicates(["sym", "setup", "tf", "mgmt"])
    cols = ["sym", "setup", "tf", "mgmt", "variant", "n", "wr", "exp", "exp_unw", "size", "cost", "n_is", "exp_is",
            "wr_is", "n_oos", "exp_oos", "wr_oos", "months_pos", "months"]
    return json.loads(g[cols].round(4).to_json(orient="records"))


def _trades_json(x: pd.DataFrame) -> list[dict]:
    if not len(x):
        return []
    cols = [c for c in ("ts", "sym", "tf", "setup", "variant", "mgmt", "side", "r", "w", "rw", "exit", "p", "week") if c in x.columns]
    y = x.sort_values("ts")[cols].copy()
    y["ts"] = y["ts"].astype(str)
    return json.loads(y.round(4).to_json(orient="records"))


def _atomic_write(path: Path, text: str) -> None:
    """Write-then-rename, so the live app never reads a half-written playbook."""
    import os
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def build(cfg, robustness: bool = True) -> dict:
    """Validate the policy by walk-forward, choose today's playbook, write playbook.json + the
    dashboard's research summary. Returns the summary."""
    from .research import research_dir
    p = trades_path(cfg)
    if not p.exists():
        raise FileNotFoundError(f"{p} — run the research grid first (python run_research.py)")
    trades = pd.read_pickle(p)
    from .research import own_trades
    own = own_trades(trades)            # per-cell statistics: each cell's own one-at-a-time record
    pol = policy_from_cfg(cfg)
    cube = load_cube(cfg)
    days = cube.days
    oos_from = days[int(len(days) * 2 / 3)]
    wf_start = days[min(20, len(days) - 1)]
    wf = walk_forward(trades, pol, start_day=wf_start, cube=cube)
    pf = portfolio(wf, pol)
    # calibration of the win-probability estimate on unseen weeks (before capacity)
    calib = []
    wfo = own_trades(wf)                # each selected cell's own one-at-a-time trades (busy_self candidates dropped)
    if len(wfo):
        b = pd.cut(wfo["p"], [0, 0.45, 0.5, 0.55, 0.6, 0.65, 1.0])
        val = "rw" if "rw" in wfo.columns else "r"
        for k, g in wfo.groupby(b, observed=True):
            calib.append({"bucket": str(k), "n": int(len(g)), "p_est": round(float(g["p"].mean()), 3),
                          "win_rate": round(float((g["r"] > 0).mean()), 3), "avg_r": round(float(g[val].mean()), 3)})
    rob = []
    if robustness:
        for win in (30, 45, 60):
            for mn in (20, 25, 35):
                for ncell in (5, 10):
                    for mp in (0.45, 0.5):
                        q = deepcopy(pol); q.window_days, q.min_n = win, mn
                        q.instruments["XAUUSD"] = InstrumentRule(**{**asdict(q.instruments.get("XAUUSD", InstrumentRule("core"))),
                                                                    "max_cells": ncell, "min_p": mp})
                        x = portfolio(walk_forward(trades, q, start_day=wf_start, cube=cube), q)
                        rob.append({"window": win, "min_n": mn, "xau_cells": ncell, "xau_min_p": mp, **summarize(x)})
    # does a cell's past predict its future? (in-sample vs out-of-sample expectancy across cells)
    val = cube.val
    tt = own.assign(_oos=own["day"] >= oos_from)
    g = tt.groupby(KEY + ["_oos"])[val].agg(["size", "mean"]).unstack("_oos")
    g.columns = ["n_is", "n_oos", "e_is", "e_oos"]
    g = g.dropna()
    g = g[(g["n_is"] >= 20) & (g["n_oos"] >= 10)]
    persistence = {"cells": int(len(g)),
                   "corr": round(float(g["e_is"].corr(g["e_oos"])), 3) if len(g) > 5 else None,
                   "both_positive": round(float(((g["e_is"] > 0) & (g["e_oos"] > 0)).mean()), 3) if len(g) else None,
                   "chance": round(float((g["e_is"] > 0).mean() * (g["e_oos"] > 0).mean()), 3) if len(g) else None}
    periods = json.loads(tt[tt["mgmt"] == "std"].groupby(["sym", "_oos"])[val].mean().round(4).unstack("_oos")
                         .rename(columns={False: "in_sample", True: "out_of_sample"}).reset_index().to_json(orient="records"))
    asof = (pd.Timestamp(days[-1]) + pd.Timedelta(days=1)).date()
    current = with_pinned(cfg, select_asof(cfg, asof, pol))
    # watchlist: index cells closest to the 60% bar
    st = score(cube.window(len(days) - pol.window_days, len(days)), pol)
    idx = st[st["sym"].map(lambda s: _rule(pol, s).role == "selective") & (st["n"] >= 15) & st["tf"].isin(pol.tfs)]
    watch = idx.sort_values("p", ascending=False).drop_duplicates(["sym", "tf", "setup", "mgmt"]).head(12)
    watch = [{**c, "eligible": bool(e)} for c, e in zip(cells_json(watch), eligible(watch, pol))]
    meta = json.loads((research_dir(cfg) / "trades_meta.json").read_text()) if (research_dir(cfg) / "trades_meta.json").exists() else {}
    per = {}
    for sym in sorted(trades["sym"].unique()):
        xs = pf[pf["sym"] == sym] if len(pf) else pf
        per[sym] = {"role": _rule(pol, sym).role, "rule": asdict(_rule(pol, sym)),
                    "walk_forward": summarize(xs), "cells": [c for c in current["cells"] if c["sym"] == sym],
                    "watch": [w for w in watch if w["sym"] == sym]}
    summary = {
        "created": pd.Timestamp.now(tz=cfg["timezone"]).isoformat(timespec="seconds"),
        "data": {"from": str(days[0]), "to": str(days[-1]), "days": len(days), "oos_from": str(oos_from),
                 "walk_forward_from": str(wf_start), "trades": int(len(own)), "candidates": int(len(trades)), "grid": meta},
        "policy": pol.to_json(),
        "walk_forward": {"summary": summarize(pf), "before_capacity": summarize(wfo), "trades": _trades_json(pf),
                         "by_symbol": {s: summarize(pf[pf["sym"] == s]) for s in pf["sym"].unique()} if len(pf) else {},
                         # weekly sums in the SAME units as the headline (`units`: rw = budget-weighted), so
                         # they add up to summary.sum_r; r_unw = the same trades in plain per-trade R
                         "units": cube.val,
                         "weekly": (pf.groupby("week").agg(n=(cube.val, "size"), r=(cube.val, "sum"), r_unw=("r", "sum"))
                                    .round(4).reset_index().to_dict("records") if len(pf) else [])},
        "calibration": calib, "robustness": rob, "instruments": per, "heat": _heat(own, oos_from),
        "persistence": persistence, "periods": periods,
        "costs": json.loads(own.groupby(["sym", "tf"]).agg(cost_r=("cost_r", "mean"),
                                                           size=("w", "mean") if "w" in own.columns else ("cost_r", "size"))
                            .round(4).reset_index().to_json(orient="records")),
        "units": "rw" if "rw" in trades.columns else "r",
        "playbook": current,
    }
    out = research_dir(cfg)
    out.mkdir(parents=True, exist_ok=True)
    _atomic_write(out / "summary.json", json.dumps(summary, default=str))
    _atomic_write(playbook_path(cfg), json.dumps({**current, "created": summary["created"],
                                                  "validation": summary["walk_forward"]["summary"]}, indent=1, default=str))
    log.info("playbook: %d cells (%s) · walk-forward %s", len(current["cells"]),
             ", ".join(f"{s}:{sum(c['sym'] == s for c in current['cells'])}" for s in per), summary["walk_forward"]["summary"])
    return summary
