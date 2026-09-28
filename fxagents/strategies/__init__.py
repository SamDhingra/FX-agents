"""Strategy registry + the Confluence strategy the learner uses to invent new strategies."""
from __future__ import annotations

import pandas as pd

from .base import RawSignal, Strategy
from .classic import MACDCross, RSIReversion, SRRejection
from .smc import (DTFXZone, ICTFvgSweep, ICTOte, SMCBreaker, SMCInverseFVG, SMCLiquiditySweep,
                  SMCOrderBlock, StoicSBS)

BUILTIN: dict[str, type[Strategy]] = {c.name: c for c in
                                      (ICTFvgSweep, ICTOte, DTFXZone, StoicSBS, SMCOrderBlock, SMCBreaker,
                                       SMCInverseFVG, SMCLiquiditySweep, SRRejection, RSIReversion, MACDCross)}


class Confluence(Strategy):
    """Primary entry model + one or more filters that must agree on direction.
    e.g. stoic_sbs entries taken only when dtfx structure bias and MACD histogram agree."""
    name = "confluence"
    family = "confluence"
    description = "Learner-generated: primary strategy entries filtered by other strategies' directional bias."

    def __init__(self, params: dict, version: str = "v1", rr: float = 1.0, status: str = "candidate",
                 origin: str = "learner", tf: str = "5min") -> None:
        super().__init__(params, version, rr, status, origin, tf)
        self.primary = build_strategy(params["primary"])
        self.filters = [build_strategy(f) for f in params["filters"]]

    @property
    def id(self) -> str:
        return f"{self.primary.name}+{'+'.join(f.name for f in self.filters)}:{self.tf_label}@{self.version}"

    def _scan(self, df, ctx):
        sigs = self.primary.scan(df, ctx)
        biases = [f.bias(df, ctx).to_numpy() for f in self.filters]
        out: list[RawSignal] = []
        for s in sigs:
            if all(b[s.i] * s.side > 0 for b in biases):
                s.reason = f"{s.reason} | confluence: {', '.join(f.name for f in self.filters)}"
                out.append(s)
        return out

    def bias(self, df, ctx) -> pd.Series:
        return self.primary.bias(df, ctx)


def build_strategy(spec: dict) -> Strategy:
    cls = spec["class"]
    kw = dict(version=spec.get("version", "v1"), rr=spec.get("rr", 1.0),
              status=spec.get("status", "live"), origin=spec.get("origin", "builtin"), tf=spec.get("tf", "5min"))
    st = Confluence(spec["params"], **kw) if cls == "confluence" else BUILTIN[cls](spec.get("params"), **kw)
    st.created = spec.get("created")  # type: ignore[attr-defined]
    return st


def default_specs(rr: float = 1.0, tfs: tuple[str, ...] = ("5min", "15min")) -> list[dict]:
    """Every builtin strategy on every entry timeframe; the 5m and 15m versions compete hourly."""
    return [c(tf=tf).spec() | {"rr": rr} for tf in tfs for c in BUILTIN.values()]


__all__ = ["Strategy", "RawSignal", "BUILTIN", "Confluence", "build_strategy", "default_specs"]
