"""The plugin API. A strategy is a small Python class in btplugins/ — it only says WHEN to enter and WHERE the stop and
target are; the engine does everything else the same way for every strategy (real bid/ask fills, slippage, costs,
exits, controls, statistics, the look-ahead audit and the seen/vault protocol).

    from fxagents.bt import Strategy, Signal, Exits, ind

    class MyIdea(Strategy):
        name = "my_idea_v1"
        symbol = "XAUUSD"
        exits = Exits(target_r=2.0, be_at_r=1.0, flat_at=950)      # 15:50 NY
        entry_windows = [(480, 690)]                                # fills 08:00–11:30 NY
        max_per_day = 1

        def signals(self, m):                                       # m = fxagents.bt.data.Market
            b = m.bars(15)
            e = ind.ema(b.c, 50)
            out = []
            for i in range(51, len(b)):
                if b.c.iloc[i] > e[i] and b.c.iloc[i - 1] <= e[i - 1]:
                    out.append(Signal(t=int(b.end.iloc[i]), side=1, stop=float(b.l.iloc[i])))
            return out

Rules for plugins: a Signal's `t` is the moment the decision is known (a candle's `end`); use only data that existed by
then. The engine re-runs a sample of signals on data that stops at `t` and flags any that change (look-ahead audit).
Prices in Signals are real prices (not mirrored). Use `params` for anything you might vary, so variants and the
fingerprint capture them.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass
class Signal:
    t: int                              # ns — when the decision is known (a candle's end)
    side: int                           # +1 long, −1 short
    stop: float                         # protective stop (real price)
    entry: str = "market"               # market (next minute's open) | limit | stop
    price: float | None = None          # limit / stop-entry price
    expire_min: float = 0.0             # pending order life (minutes); market: max wait for the next minute (0 → 5)
    cancel: float | None = None         # cancel the pending order if the mid price touches this level first
    target: float | None = None         # full-exit target (real price) — overrides exits.target_r
    exit_t: int | None = None           # ns: the strategy's own exit decision (e.g. a daily close where its exit rule
                                        # fired) — out at the first minute at/after it, if still open
    risk_min: float | None = None       # skip unless the risk at fill (price) is within [risk_min, risk_max]
    risk_max: float | None = None
    tag: str = ""                       # free label (shown on the chart and in the trade list)
    draw: list = field(default_factory=list)   # chart drawings: {"k": "line"|"box"|"mark", "t0", "t1", "px"|"hi","lo", "label"}
    exits: dict | None = None           # per-signal overrides of Exits fields
    info: dict = field(default_factory=dict)


@dataclass
class Exits:
    target_r: float | None = None       # full exit at +x R (None = no fixed target)
    partials: list = field(default_factory=list)   # [(at_R, fraction, new_stop_R or None), …] e.g. [(1.5, 0.7, 0.2)]
    be_at_r: float | None = None        # once the best price reaches +x R …
    be_lock_r: float = 0.0              # … the stop moves to entry + y R
    trail: dict | None = None           # {"kind": "chandelier", "tf": "4h", "atr": 14, "k": 2.2, "src": "close"}
                                        # {"kind": "swing", "tf": 15, "k": 2, "buf_r": 0.0}
                                        # {"kind": "gap_r", "gap": 1.0}
    trail_after_r: float = 0.0          # trailing starts once the best price reached this many R
    max_hold_min: float | None = None
    flat_at: int | None = None          # NY minute of day: out at that minute's open (e.g. 950 = 15:50)
    friday_flat_at: int | None = None   # NY minute on Fridays (no weekend holds)
    time_stop: tuple | None = None      # (minutes, min_R): out if after `minutes` the trade is below min_R
    hold_overnight: bool = False        # allow holding across 17:00 NY (financing charged)


@dataclass
class Costs:
    stop_slip_frac: float = 0.15        # intrabar stop fills pay this share of the spread (stops are market orders)
    cad: bool = True                    # OANDA Canada 1% conversion: wins × 0.99, losses × 1.01
    financing_bps: float = 1.8          # per 17:00 NY rollover, of the entry price (≈ 6.5% a year)
    triple_dow: int | None = 2          # weekday charged 3× (2 = Wednesday); None for crypto (charged every day)
    rollover_shield: tuple = (1015, 1085)   # 16:55–18:05 NY: stops trigger on the MID only (spread spikes)
    same_bar_check: bool = True         # after a partial / stop move, the same minute's low can still stop the rest
    gap_exit_min: float = 60.0          # a data gap longer than this exits at the last price before it
    max_spread_frac: float | None = None    # skip a fill if the spread exceeds this share of the risk


CRYPTO = ("BTCUSD", "ETHUSD")                # trade every day: financing is charged daily, weekends too (no triple)


def costs_for(costs: Costs, symbol: str) -> Costs:
    return replace(costs, triple_dow=None) if symbol in CRYPTO and costs.triple_dow is not None else costs


class Strategy:
    """Subclass this. Required: name, symbol, signals(m). Everything else has a default."""
    name = "unnamed"
    symbol = "XAUUSD"
    description = ""
    params: dict[str, Any] = {}
    exits = Exits()
    costs = Costs()
    entry_windows: list | None = None   # [(start_mod, end_mod), …] NY minutes allowed for the FILL; None = any time
    max_per_day: int | None = None      # per trading day (18:00 NY → 18:00)
    one_at_a_time: bool = True
    news_block: tuple | None = (15, 15) # minutes before/after FOMC/CPI/NFP/PPI with no fills; None = off
    news_10am: bool = False             # also block ±5 min around 10:00 NY every weekday (ISM, JOLTS …)
    warmup_days: int = 90               # history the look-ahead audit gives each re-run (longer for slow indicators)
    variants: dict[str, dict] = {}      # extra controls: name → params override (e.g. {"no_bias": {"use_bias": False}})

    def __init__(self, **overrides):
        self.params = {**type(self).params, **overrides}

    def p(self, k):
        return self.params[k]

    def signals(self, m) -> list[Signal]:      # pragma: no cover - plugins implement it
        raise NotImplementedError

    def adjust(self, trade: dict, m, k: int) -> float | None:
        """Optional: called at every minute k while a trade is open; return a new stop (real price) to ratchet it
        (only moves that reduce risk are applied). `trade` (side, entry, stop0, risk, j = fill minute, signal) is the
        same dict for the whole trade, so a plugin can keep its own state in it."""
        return None

    def with_params(self, **overrides) -> "Strategy":
        return type(self)(**{**self.params, **overrides})

    def exits_for(self, s: Signal) -> Exits:
        return replace(self.exits, **s.exits) if s.exits else self.exits
