"""Pips and lots for display. The bot itself sizes in broker units by risk; these are only the trader's
way of reading the same numbers.

Conventions (override per instrument in config: `pip_size`, `lot_units`):
  XAUUSD  1 pip = $0.10 of price (MT4/MT5 convention, 1 point of gold = 10 pips); 1 lot = 100 oz
          (OANDA units are ounces, so 10 units = 0.10 lot; one IBKR MGC contract = 10 oz = 0.10 lot)
  indices 1 pip = 1 index point; 1 lot = $1 per point (one OANDA unit of US30/NAS100/SPX500; one MES
          contract = $5/pt = 5 lots)
Lots = units × contract multiplier ÷ lot size, so the same position reads the same on either broker."""
from __future__ import annotations

PIP = {"XAUUSD": 0.1, "SPX": 1.0, "NDQ": 1.0, "US30": 1.0}
LOT = {"XAUUSD": 100.0, "SPX": 1.0, "NDQ": 1.0, "US30": 1.0}


def pip_size(cfg, sym: str) -> float:
    return float((cfg.get("instruments", {}).get(sym) or {}).get("pip_size") or PIP.get(sym, 1.0))


def lot_units(cfg, sym: str) -> float:
    return float((cfg.get("instruments", {}).get(sym) or {}).get("lot_units") or LOT.get(sym, 1.0))


def _r(x, n=1):
    return None if x is None else round(float(x), n)


def position(cfg, d: dict) -> dict:
    """Adds lots and pips to Position.to_public()."""
    sym, side = d["symbol"], 1 if d["side"] == "LONG" else -1
    pip, lot = pip_size(cfg, sym), lot_units(cfg, sym)
    mult = float((cfg["instruments"].get(sym) or {}).get("multiplier", 1))
    d["lots"] = _r(d["qty"] * mult / lot, 2)
    d["lots_initial"] = _r(d["initial_qty"] * mult / lot, 2)
    d["pips_now"] = _r((d["price"] - d["avg_entry"]) * side / pip)
    d["stop_pips"] = _r(abs(d["entry"] - d["initial_stop"]) / pip)            # initial risk
    d["locked_pips"] = _r((d["stop"] - d["avg_entry"]) * side / pip)          # >0 = stop in profit
    d["pip_value"] = _r(pip * lot, 2)                                          # $ per pip per lot
    return d


def trade(cfg, t: dict) -> dict:
    """Adds lots and pips to a journal trade row. `pips` = net P&L ÷ ($ per pip × all units traded),
    i.e. the average pips captured per unit (partials and adds included)."""
    sym = t.get("symbol")
    if not sym:
        return t
    pip, lot = pip_size(cfg, sym), lot_units(cfg, sym)
    mult = float((cfg["instruments"].get(sym) or {}).get("multiplier", 1))
    q0, qg = t.get("qty_initial") or 0, t.get("qty_gross") or t.get("qty_initial") or 0
    t["lots"] = _r(q0 * mult / lot, 2)
    t["lots_max"] = _r(qg * mult / lot, 2)
    t["risk_pips"] = _r(abs((t.get("entry") or 0) - (t.get("initial_stop") or 0)) / pip) if t.get("initial_stop") else None
    t["pips"] = _r(t["realized"] / (mult * pip * qg)) if t.get("realized") is not None and qg else None
    return t
