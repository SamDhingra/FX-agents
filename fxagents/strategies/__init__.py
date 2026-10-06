"""Strategy registry + the Confluence strategy the learner uses to invent new strategies."""
from __future__ import annotations

import pandas as pd

from .base import RawSignal, Strategy
from .classic import MACDCross, RSIReversion, SRRejection
from .article_setups import LondonBreakout
from .confluence import ZoneConfluence
from .dtfx import DTFXCloseFib, DTFXCloseFibBreak, DTFXCloseOrigin, DTFXWickFib
from .ict import ICT2022, ICTAMD, ICTSilverBullet, ICTTurtleSoup, SMTDivergence
from .smc import (DTFXZone, ICTFvgSweep, ICTOte, SMCBreaker, SMCInverseFVG, SMCLiquiditySweep,
                  SMCOrderBlock, StoicSBS)
from .structure_setups import SMCBosRetest, SMCChochRetest, SMCDisplacement, SMCMss, VWAPSetup

BUILTIN: dict[str, type[Strategy]] = {c.name: c for c in
                                      (ICTFvgSweep, ICTOte, DTFXZone, StoicSBS, SMCOrderBlock, SMCBreaker,
                                       SMCInverseFVG, SMCLiquiditySweep, SRRejection, RSIReversion, MACDCross)}

# Setups added for the playbook strategy. Kept out of BUILTIN so the hourly-pick book (and its default
# strategy list in fresh journals / replays) is unchanged; build_strategy resolves both.
SETUPS: dict[str, type[Strategy]] = {c.name: c for c in
                                     (ICT2022, ICTSilverBullet, ICTTurtleSoup, ICTAMD, SMTDivergence,
                                      SMCDisplacement, SMCBosRetest, SMCChochRetest, SMCMss,
                                      DTFXCloseFib, DTFXWickFib, DTFXCloseFibBreak, DTFXCloseOrigin, VWAPSetup,
                                      ZoneConfluence, LondonBreakout)}
ALL: dict[str, type[Strategy]] = {**BUILTIN, **SETUPS}


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
    st = Confluence(spec["params"], **kw) if cls == "confluence" else ALL[cls](spec.get("params"), **kw)
    st.created = spec.get("created")  # type: ignore[attr-defined]
    st.vetted = bool(spec.get("vetted", False))  # type: ignore[attr-defined]  # approved for LIVE trading
    st.meta = spec.get("meta") or {}  # type: ignore[attr-defined]       # learner: parent, change, kind
    return st


def default_specs(rr: float = 1.0, tfs: tuple[str, ...] = ("5min", "15min")) -> list[dict]:
    """Every builtin strategy on every entry timeframe; the 5m and 15m versions compete hourly."""
    return [c(tf=tf).spec() | {"rr": rr} for tf in tfs for c in BUILTIN.values()]


__all__ = ["Strategy", "RawSignal", "BUILTIN", "SETUPS", "ALL", "Confluence", "build_strategy", "default_specs"]
