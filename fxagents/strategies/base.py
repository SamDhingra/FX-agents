from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from .. import indicators as ind


@dataclass
class RawSignal:
    i: int                 # bar index whose CLOSE triggers the entry
    side: int
    entry: float
    stop: float
    reason: str
    structural_target: float | None = None
    features: dict = field(default_factory=dict)


class Strategy:
    """A strategy is a pure function of bars → signals.

    `scan()` walks the whole frame causally and returns every signal it would have taken, so the
    same code powers live trading (take the signal on the last bar), the rolling evaluation that
    ranks strategies each hour, and the learner's parameter search.
    """

    name: ClassVar[str] = "base"
    family: ClassVar[str] = "base"
    description: ClassVar[str] = ""
    default_params: ClassVar[dict[str, Any]] = {}
    param_grid: ClassVar[dict[str, list]] = {}

    def __init__(self, params: dict | None = None, version: str = "v1", rr: float = 1.0,
                 status: str = "live", origin: str = "builtin", tf: str = "5min") -> None:
        self.params = {**self.default_params, **(params or {})}
        self.tf = tf            # entry timeframe: "5min" | "15min" (anything pandas understands)
        self.version = version
        self.rr = rr
        self.status = status  # live | shadow | candidate | retired
        self.origin = origin

    # ── identity ──────────────────────────────────────────────────────────
    @property
    def tf_label(self) -> str:
        return f"{int(pd.Timedelta(self.tf).total_seconds() // 60)}m"

    @property
    def id(self) -> str:
        return f"{self.name}:{self.tf_label}@{self.version}"

    def spec(self) -> dict:
        return {"id": self.id, "class": self.name, "version": self.version, "params": self.params, "tf": self.tf,
                "rr": self.rr, "status": self.status, "origin": self.origin, "family": self.family,
                "created": getattr(self, "created", None), "vetted": bool(getattr(self, "vetted", False)),
                "meta": getattr(self, "meta", None) or {}}

    # ── to implement ──────────────────────────────────────────────────────
    def _scan(self, df: pd.DataFrame, ctx: dict) -> list[RawSignal]:
        raise NotImplementedError

    def bias(self, df: pd.DataFrame, ctx: dict) -> pd.Series:
        """Directional opinion per bar (+1/0/-1). Used when the learner composes confluence strategies."""
        return pd.Series(0, index=df.index)

    # ── shared plumbing ───────────────────────────────────────────────────
    @staticmethod
    def context(df: pd.DataFrame) -> dict:
        """Indicators computed once per frame and shared by every strategy scanning it."""
        c = df["close"]
        bar_delta = pd.Series(df.index).diff().median() if len(df) > 2 else pd.Timedelta("5min")
        line, sig, hist = ind.macd(c)
        return {
            "atr": ind.atr(df).to_numpy(),
            "ema50": ind.ema(c, 50).to_numpy(),
            "ema200": ind.ema(c, 200).to_numpy(),
            "rsi": ind.rsi(c).to_numpy(),
            "macd": line.to_numpy(), "macd_sig": sig.to_numpy(), "macd_hist": hist.to_numpy(),
            "adx": ind.adx(df).to_numpy(),
            "htf": ind.htf_bias(df).to_numpy() if len(df) > 60 else np.zeros(len(df)),
            "close_ts": df.index + bar_delta,
            "_pivots": {},
        }

    @staticmethod
    def pivots(df: pd.DataFrame, ctx: dict, left: int, right: int) -> list[ind.Pivot]:
        key = (left, right)
        if key not in ctx["_pivots"]:
            ctx["_pivots"][key] = ind.pivots(df, left, right)
        return ctx["_pivots"][key]

    def scan(self, df: pd.DataFrame, ctx: dict | None = None) -> list[RawSignal]:
        ctx = ctx or self.context(df)
        out = []
        a = ctx["atr"]
        for s in self._scan(df, ctx):
            risk = abs(s.entry - s.stop)
            if risk <= 0 or not np.isfinite(risk):
                continue
            s.features.setdefault("atr", float(a[s.i]))
            s.features.setdefault("risk_atr", float(risk / a[s.i]) if a[s.i] else None)
            out.append(s)
        return out

    def variants(self, max_n: int = 8, rng: np.random.Generator | None = None) -> list[dict]:
        """Parameter sets for the learner to try (random subset of the grid)."""
        if not self.param_grid:
            return []
        keys = list(self.param_grid)
        combos = [dict(zip(keys, vals)) for vals in itertools.product(*self.param_grid.values())]
        combos = [c for c in combos if {**self.params, **c} != self.params]
        rng = rng or np.random.default_rng()
        if len(combos) > max_n:
            combos = [combos[j] for j in rng.choice(len(combos), max_n, replace=False)]
        return combos


def in_window(ctx: dict, i: int, windows: list[list[str]] | None) -> bool:
    return True if not windows else ind.in_windows(ctx["close_ts"][i], windows)
