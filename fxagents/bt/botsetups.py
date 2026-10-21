"""The bridge behind the per-setup plugins in btplugins/ (ict_amd.py, dtfx_close_fib.py, …): runs the trading bot's OWN
setup code (fxagents/strategies) through the backtest engine with the bot's live rules, as closely as the engine allows.

Live rules applied (config.yaml as of 2026-10-20):
  entries only in the windows 02:00–05:00, 08:30–11:30, 13:30–15:30, 20:00–23:59 NY, never against the 1H/4H/daily
  structure bias (side × score ≥ 0.25; the "no_bias" variant drops it), not around FOMC/CPI/NFP/PPI;
  stops tighter than 0.5 ATR widened to 0.5 ATR, wider than 10% of price skipped; one trade at a time per setup;
  first target 1R: bank 50%, stop to +0.1R; every further +1R the stop steps up 1R; after the first target, 45 min
  without a new best price tightens the stop to best − 0.5R; out after 4 hours or at 15:50 NY.
Not modelled: adds (off in live anyway), Jev's quality gate, the portfolio caps across instruments.

`mgmt` (Oct 21 2026) swaps the trade management, everything else unchanged — to test on years what the replay of the
bot's real trades (./fx.sh mgmtreplay) suggested:  live (default, the rules above) · stop_only · target_2r · target_3r ·
cut15 / cut30 (out if not above 0R after 15 / 30 min, else 2R) · cut15_3r. All keep the 4-hour / 15:50 exits.
A plugin's recorded code fingerprint covers this file and the bot's setup code too (fxagents/bt/run.code_sha).
"""
import numpy as np
import pandas as pd

from .api import Exits, Signal, Strategy

LIVE_WINDOWS = [(120, 300), (510, 690), (810, 930), (1200, 1440)]
MGMT = {"live": None,                                         # the class's own exits + the stall rule in adjust()
        "stop_only": {"partials": [], "target_r": None},
        "target_2r": {"partials": [], "target_r": 2.0},
        "target_3r": {"partials": [], "target_r": 3.0},
        "cut15": {"partials": [], "target_r": 2.0, "time_stop": (15, 0.0)},
        "cut30": {"partials": [], "target_r": 2.0, "time_stop": (30, 0.0)},
        "cut15_3r": {"partials": [], "target_r": 3.0, "time_stop": (15, 0.0)}}


class BotSetup(Strategy):
    name = "bot_setup"
    symbol = "BTCUSD"
    description = "The bot's own setup code with its live rules."
    params = {"setup": "ict_silver_bullet", "tf": "5min", "setup_params": {}, "use_bias": True, "min_align": 0.25,
              "min_stop_atr": 0.5, "max_stop_pct": 0.10, "stall_min": 45, "stall_gap_r": 0.5, "mgmt": "live"}
    exits = Exits(partials=[(1.0, 0.5, 0.1)] + [(float(k), 0.0, k - 0.9) for k in range(2, 9)],
                  max_hold_min=240, flat_at=950)
    entry_windows = LIVE_WINDOWS
    news_block = (15, 15)
    variants = {"no_bias": {"use_bias": False}}
    warmup_days = 90                      # the bias needs ≥ 20 trading days of 1H history to settle

    def _frame(self, m):
        b = m.bars(int(pd.Timedelta(self.p("tf")).total_seconds() // 60))
        df = b[["o", "h", "l", "c", "v"]].set_axis(["open", "high", "low", "close", "volume"], axis=1)
        return b, df

    def signals(self, m):
        from fxagents.research import _signals, verify_live_window
        from fxagents.strategies import ALL, Strategy as BotStrategy, build_strategy
        P = self.params
        cls = ALL[P["setup"]]
        if cls.needs_peers:
            raise ValueError(f"{P['setup']} needs a correlated second instrument")
        st = build_strategy({"class": P["setup"], "tf": P["tf"], "params": P["setup_params"]})
        b, df = self._frame(m)
        if len(df) < 300:
            return []
        ctx = BotStrategy._context(df)
        ctx["peers"] = []
        sigs = sorted(_signals(st, df, ctx), key=lambda s: s.i)
        if not getattr(cls, "fast", False):
            sigs = [s for s in sigs if verify_live_window(st, df, s.i, s.side)]
        end = b.end.to_numpy()
        when = pd.DatetimeIndex(pd.to_datetime(end[[s.i for s in sigs]], utc=True)) if sigs else None
        score = np.zeros(len(sigs))
        if P["use_bias"] and sigs:
            from fxagents.bias import bias_frame
            h = m.bars("1h")
            h1 = h[["o", "h", "l", "c"]].set_axis(["open", "high", "low", "close"], axis=1)
            uw = when.unique().sort_values()
            sc = bias_frame(h1, uw.tz_convert(h1.index.tz))["score"].to_numpy()
            score = sc[uw.get_indexer(when)]
        a, c = ctx["atr"], df["close"].to_numpy()
        out = []
        for n, s in enumerate(sigs):
            i = s.i
            if not np.isfinite(a[i]):
                continue
            if P["use_bias"] and not (np.isfinite(score[n]) and s.side * score[n] >= P["min_align"]):
                continue
            stop = float(s.stop)
            if abs(c[i] - stop) < P["min_stop_atr"] * a[i]:
                stop = float(c[i] - s.side * P["min_stop_atr"] * a[i])
            if (c[i] - stop) * s.side <= 0 or abs(c[i] - stop) / c[i] > P["max_stop_pct"]:
                continue
            draw = [{**d, **{k: int(pd.Timestamp(d[k]).value) for k in ("t0", "t1") if d.get(k)}}
                    for d in (s.features.get("draw") or [])]
            out.append(Signal(t=int(end[i]), side=int(s.side), stop=stop, tag=P["setup"],
                              draw=draw, info={"reason": s.reason}, exits=MGMT[P.get("mgmt", "live")]))
        return out

    def adjust(self, trade, m, k):
        """The live runner rule: after the first target, 45 min without a new best → stop to best − 0.5R."""
        P, side, e, R = self.params, trade["side"], trade["entry"], trade["risk"]
        if P.get("mgmt", "live") != "live":
            return None
        px = m.h[k] if side > 0 else m.l[k]
        if "best" not in trade or side * px > side * trade["best"]:
            trade["best"], trade["best_k"] = px, k
        if side * (trade["best"] - e) < R or k - trade["best_k"] < P["stall_min"]:
            return None
        return float(trade["best"] - side * P["stall_gap_r"] * R)
