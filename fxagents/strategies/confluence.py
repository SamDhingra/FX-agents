"""Zone confluence: trade only when two or more DIFFERENT zone setups agree.

The idea (order block + FVG, order block + breaker, …): when separate zone definitions fire in the same
direction at the same time, the level is "stacked" and should hold more often. This class runs its
component setups on the same bars and emits a signal on bar i when at least `need` distinct components
have a same-side signal within the last `within` bars (i included). The entry is bar i's close; the stop
is the most protective (farthest) of the agreeing components' stops, so no component's invalidation is
inside the trade. The structural target is the nearest of theirs.

It is a research candidate like every other setup: the weekly research measures it on the same grid,
and the playbook only trades it if it holds up out of sample. Agreement is not a guarantee — in the
first offline check (Oct 2026, 64 days) same-bar agreement between zone setups won ~43%, the same as
the zones on their own.
"""
from __future__ import annotations

from .base import RawSignal, Strategy

ZONE_SETUPS = ("smc_order_block", "smc_breaker", "smc_ifvg", "ict_fvg_sweep", "ict_ote")


class ZoneConfluence(Strategy):
    name = "zone_confluence"
    family = "confluence"
    description = ("Two or more different zone setups (order block, breaker, inverse FVG, FVG after a sweep, OTE) "
                   "fire the same way within a few bars — entry on the bar the agreement completes, stop beyond "
                   "the farthest of their stops.")
    default_params = dict(need=2, within=2, components="zones")
    param_grid = {"need": [2, 3], "within": [0, 2, 4], "components": ["zones", "ob_fvg"]}

    def _components(self):
        from . import ALL
        names = ("smc_order_block", "smc_ifvg", "ict_fvg_sweep") if self.params["components"] == "ob_fvg" else ZONE_SETUPS
        return [(n, ALL[n](tf=self.tf)) for n in names if n in ALL]

    def _scan(self, df, ctx):
        p = self.params
        by_bar: dict[int, list[tuple[str, RawSignal]]] = {}
        for name, st in self._components():
            try:
                sigs = st._scan_full(df, ctx)
            except Exception:  # noqa: BLE001 — one broken component never kills the stack
                continue
            for s in sigs:
                by_bar.setdefault(s.i, []).append((name, s))
        out, used = [], set()
        for i in sorted(by_bar):
            for side in (1, -1):
                if not any(s.side == side for _, s in by_bar[i]):
                    continue                       # the agreement completes on a bar where a component fires
                agree: dict[str, RawSignal] = {}
                for k in range(max(0, i - p["within"]), i + 1):
                    for name, s in by_bar.get(k, []):
                        if s.side == side:
                            agree[name] = s        # latest signal per component
                if len(agree) < p["need"] or (i, side) in used:
                    continue
                used.add((i, side))
                stops = [s.stop for s in agree.values()]
                stop = min(stops) if side > 0 else max(stops)
                tgts = [s.structural_target for s in agree.values() if s.structural_target is not None]
                tgt = (min(tgts) if side > 0 else max(tgts)) if tgts else None
                entry = float(df["close"].iloc[i])
                if (entry - stop) * side <= 0:
                    continue
                out.append(RawSignal(i, side, entry, stop, "Confluence: " + " + ".join(sorted(agree)),
                                     structural_target=tgt, features={"n_agree": len(agree)}))
        return out
