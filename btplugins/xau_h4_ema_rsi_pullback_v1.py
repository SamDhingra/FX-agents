from fxagents.bt import Strategy, Signal, Exits, Costs, ind
import numpy as np


class XauH4EmaRsiPullbackV1(Strategy):
    name = "xau_h4_ema_rsi_pullback_v1"
    symbol = "XAUUSD"
    description = (
        "Symmetric 1H RSI(7) pullback-and-turn inside a 4H EMA(20/50) trend on XAUUSD, "
        "requiring >= 0.75R room to the 20-bar 4H structural high/low."
    )
    params = {
        "ema_fast_n": 20,
        "ema_slow_n": 50,
        "use_h4_ema": 1,
        "rsi_n": 7,
        "rsi_win": 35,
        "rsi_os": 38.0,
        "rsi_ob": 62.0,
        "sr_lookback_h4": 20,
        "min_room_r": 0.75,
        "atr_n": 14,
        "stop_atr": 1.75,
        "target_r": 2.0,
        "max_spread_frac": 0.08,
    }
    exits = Exits(
        target_r=2.0,
        max_hold_min=1440,
        friday_flat_at=990,
        hold_overnight=True,
    )
    costs = Costs(gap_exit_min=180)
    entry_windows = [(180, 960)]  # 03:00 - 16:00 NY
    max_per_day = 1
    one_at_a_time = True
    news_block = (15, 15)
    warmup_days = 120
    variants = {
        "no_h4_ema_regime": {"use_h4_ema": 0},
        "no_sr_room_filter": {"min_room_r": 0.0},
    }

    @staticmethod
    def _finite_ema(arr: np.ndarray, idx: int, n: int) -> float:
        win = min(idx + 1, 4 * n)
        seg = arr[idx - win + 1 : idx + 1]
        val = float(seg[0])
        alpha = 2.0 / (float(n) + 1.0)
        for x in seg[1:]:
            val = alpha * float(x) + (1.0 - alpha) * val
        return val

    @staticmethod
    def _finite_wilder_rsi(closes: np.ndarray, idx: int, n: int, win: int) -> float:
        start = max(0, idx - win)
        seg = closes[start : idx + 1]
        if len(seg) <= n:
            return 50.0
        diffs = np.diff(seg)
        gains = np.where(diffs > 0.0, diffs, 0.0)
        losses = np.where(diffs < 0.0, -diffs, 0.0)
        avg_g = float(np.mean(gains[:n]))
        avg_l = float(np.mean(losses[:n]))
        alpha = 1.0 / float(n)
        for k in range(n, len(diffs)):
            avg_g = (1.0 - alpha) * avg_g + alpha * float(gains[k])
            avg_l = (1.0 - alpha) * avg_l + alpha * float(losses[k])
        if avg_l <= 1e-12:
            return 100.0 if avg_g > 0.0 else 50.0
        rs = avg_g / avg_l
        return 100.0 - (100.0 / (1.0 + rs))

    def signals(self, m):
        b = m.bars("1h")
        h4 = m.bars("4h")
        if len(b) < 60 or len(h4) < 60:
            return []

        b_o = np.asarray(b.o, dtype=float)
        b_h = np.asarray(b.h, dtype=float)
        b_l = np.asarray(b.l, dtype=float)
        b_c = np.asarray(b.c, dtype=float)
        b_start = np.asarray(b.start, dtype=np.int64)
        b_end = np.asarray(b.end, dtype=np.int64)

        h4_h = np.asarray(h4.h, dtype=float)
        h4_l = np.asarray(h4.l, dtype=float)
        h4_c = np.asarray(h4.c, dtype=float)

        ema_fast_n = int(self.p("ema_fast_n"))
        ema_slow_n = int(self.p("ema_slow_n"))
        use_h4_ema = int(self.p("use_h4_ema"))
        rsi_n = int(self.p("rsi_n"))
        rsi_win = int(self.p("rsi_win"))
        rsi_os = float(self.p("rsi_os"))
        rsi_ob = float(self.p("rsi_ob"))
        sr_lookback_h4 = int(self.p("sr_lookback_h4"))
        min_room_r = float(self.p("min_room_r"))
        atr_n = int(self.p("atr_n"))
        stop_atr = float(self.p("stop_atr"))
        target_r = float(self.p("target_r"))
        max_spread_frac = float(self.p("max_spread_frac"))

        tr1h = np.empty(len(b), dtype=float)
        tr1h[0] = b_h[0] - b_l[0]
        for i in range(1, len(b)):
            tr1h[i] = max(
                b_h[i] - b_l[i],
                abs(b_h[i] - b_c[i - 1]),
                abs(b_l[i] - b_c[i - 1]),
            )

        n_min = len(m.ns)
        out = []

        for i in range(max(atr_n + 4, rsi_win + 4), len(b)):
            t_start = int(b_start[i])
            t_end = int(b_end[i])
            m_idx_start = int(m.minute_at(t_start))
            if m_idx_start >= n_min:
                continue

            # 1H bars closing in [03:00, 16:00] NY have start mod in [120, 900]
            mod_start = int(m.mod[m_idx_start])
            if mod_start < 120 or mod_start > 900:
                continue

            h4_idx = int(m.last_closed("4h", t_end))
            if h4_idx < max(ema_slow_n + 5, sr_lookback_h4 + 2):
                continue

            # Condition 1: 4H EMA(20) vs EMA(50) stack
            ema_fast = self._finite_ema(h4_c, h4_idx, ema_fast_n)
            ema_slow = self._finite_ema(h4_c, h4_idx, ema_slow_n)
            last_h4_c = float(h4_c[h4_idx])

            trend = 0
            if use_h4_ema == 1:
                if ema_fast > ema_slow and last_h4_c > ema_slow:
                    trend = 1
                elif ema_fast < ema_slow and last_h4_c < ema_slow:
                    trend = -1
                if trend == 0:
                    continue

            # Condition 2: 1H RSI(7) pullback state + turn close
            r0 = self._finite_wilder_rsi(b_c, i, rsi_n, rsi_win)
            r1 = self._finite_wilder_rsi(b_c, i - 1, rsi_n, rsi_win)
            r2 = self._finite_wilder_rsi(b_c, i - 2, rsi_n, rsi_win)

            side = 0
            if (trend == 1 or use_h4_ema == 0) and (
                min(r2, r1, r0) <= rsi_os and b_c[i] > b_o[i] and b_c[i] > b_c[i - 1]
            ):
                side = 1
            elif (trend == -1 or use_h4_ema == 0) and (
                max(r2, r1, r0) >= rsi_ob and b_c[i] < b_o[i] and b_c[i] < b_c[i - 1]
            ):
                side = -1

            if side == 0:
                continue

            atr_val = float(np.mean(tr1h[i - atr_n + 1 : i + 1]))
            if not np.isfinite(atr_val) or atr_val <= 0.0:
                continue

            stop_dist = stop_atr * atr_val

            # Condition 3: 4H structural S/R room filter (20-bar 4H high/low)
            h4_hi_20 = float(np.max(h4_h[h4_idx - sr_lookback_h4 + 1 : h4_idx + 1]))
            h4_lo_20 = float(np.min(h4_l[h4_idx - sr_lookback_h4 + 1 : h4_idx + 1]))

            if side == 1 and (h4_hi_20 - b_c[i]) < min_room_r * stop_dist:
                continue
            if side == -1 and (b_c[i] - h4_lo_20) < min_room_r * stop_dist:
                continue

            m_idx_last = min(n_min - 1, max(m_idx_start, int(m.minute_at(t_end)) - 1))
            if float(m.spread[m_idx_last]) * 1.3 > max_spread_frac * stop_dist:
                continue

            stop_price = round(float(b_c[i] - side * stop_dist), 4)
            out.append(
                Signal(
                    t=t_end,
                    side=side,
                    stop=stop_price,
                    exits={"target_r": target_r},
                    tag="xau_h4_ema_rsi_pb",
                )
            )

        return out