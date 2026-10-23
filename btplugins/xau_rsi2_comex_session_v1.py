from fxagents.bt import Strategy, Signal, Exits, Costs, ind
import numpy as np


class XauRsi2ComexSessionV1(Strategy):
    name = "xau_rsi2_comex_session_v1"
    symbol = "XAUUSD"
    description = (
        "Intraday COMEX/overlap session (09:00-16:00 NY) execution of Daily RSI(2) "
        "trend-pullback exhaustion on XAUUSD, eliminating 17:00 NY rollover financing."
    )
    params = {
        "sma_n": 40,
        "rsi_n": 2,
        "rsi_win": 20,
        "rsi_os": 15.0,
        "rsi_ob": 85.0,
        "use_sma": 1,
        "atr_n": 14,
        "bounce_atr": 0.25,
        "stop_atr": 1.50,
        "target_r": 2.0,
        "max_spread_frac": 0.10,
    }
    exits = Exits(target_r=2.0, flat_at=960, hold_overnight=False)
    entry_windows = [(540, 570)]  # 09:00 - 09:30 NY
    max_per_day = 1
    one_at_a_time = True
    news_block = (15, 15)
    warmup_days = 90
    variants = {
        "no_trend_filter": {"use_sma": 0},
    }

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
        b = m.bars(15)
        d = m.bars("1d")
        if len(b) < 40 or len(d) < 45:
            return []

        b_o = np.asarray(b.o, dtype=float)
        b_h = np.asarray(b.h, dtype=float)
        b_l = np.asarray(b.l, dtype=float)
        b_c = np.asarray(b.c, dtype=float)
        b_start = np.asarray(b.start, dtype=np.int64)
        b_end = np.asarray(b.end, dtype=np.int64)

        d_c = np.asarray(d.c, dtype=float)

        sma_n = int(self.p("sma_n"))
        rsi_n = int(self.p("rsi_n"))
        rsi_win = int(self.p("rsi_win"))
        rsi_os = float(self.p("rsi_os"))
        rsi_ob = float(self.p("rsi_ob"))
        use_sma = int(self.p("use_sma"))
        atr_n = int(self.p("atr_n"))
        bounce_atr = float(self.p("bounce_atr"))
        stop_atr = float(self.p("stop_atr"))
        target_r = float(self.p("target_r"))
        max_spread_frac = float(self.p("max_spread_frac"))

        # Causal 15m True Range array
        tr15 = np.empty(len(b), dtype=float)
        tr15[0] = b_h[0] - b_l[0]
        for i in range(1, len(b)):
            hl = b_h[i] - b_l[i]
            hc = abs(b_h[i] - b_c[i - 1])
            lc = abs(b_l[i] - b_c[i - 1])
            tr15[i] = max(hl, hc, lc)

        n_min = len(m.ns)
        out = []

        for i in range(max(atr_n + 2, 40), len(b)):
            t_start = int(b_start[i])
            t_end = int(b_end[i])
            m_idx_start = int(m.minute_at(t_start))
            if m_idx_start >= n_min:
                continue

            # Bar covering 08:45 -> 09:00 NY has start minute-of-day == 525 (08:45 NY)
            if int(m.mod[m_idx_start]) != 525:
                continue

            # Last completed daily candle at or before 09:00 NY
            d_idx = int(m.last_closed("1d", t_end))
            if d_idx < sma_n:
                continue

            sma_val = float(np.mean(d_c[d_idx - sma_n + 1 : d_idx + 1]))
            rsi_val = self._finite_wilder_rsi(d_c, d_idx, rsi_n, rsi_win)
            last_d_close = float(d_c[d_idx])

            # Causal 15m ATR over finite window [i - atr_n + 1 : i + 1]
            atr_val = float(np.mean(tr15[i - atr_n + 1 : i + 1]))
            if not np.isfinite(atr_val) or atr_val <= 0.0:
                continue

            # Overnight session (current trading session since 18:00 NY) high/low
            curr_sess = int(m.sess[m_idx_start])
            sess_high = b_h[i]
            sess_low = b_l[i]
            for k in range(i - 1, max(-1, i - 64), -1):
                mk = int(m.minute_at(int(b_start[k])))
                if mk < n_min and int(m.sess[mk]) == curr_sess:
                    if b_h[k] > sess_high:
                        sess_high = b_h[k]
                    if b_l[k] < sess_low:
                        sess_low = b_l[k]
                else:
                    break

            side = 0
            if rsi_val < rsi_os and (use_sma == 0 or last_d_close > sma_val):
                if b_c[i] > b_o[i] and (b_c[i] - sess_low) >= bounce_atr * atr_val:
                    side = 1
            elif rsi_val > rsi_ob and (use_sma == 0 or last_d_close < sma_val):
                if b_c[i] < b_o[i] and (sess_high - b_c[i]) >= bounce_atr * atr_val:
                    side = -1

            if side == 0:
                continue

            stop_dist = stop_atr * atr_val
            m_idx_last = min(n_min - 1, max(m_idx_start, int(m.minute_at(t_end)) - 1))
            curr_spread = float(m.spread[m_idx_last])
            if curr_spread * 1.3 > max_spread_frac * stop_dist:
                continue

            stop_price = round(float(b_c[i] - side * stop_dist), 4)
            target_price = round(float(b_c[i] + side * target_r * stop_dist), 4)

            out.append(
                Signal(
                    t=t_end,
                    side=side,
                    stop=stop_price,
                    target=target_price,
                    tag="xau_rsi2_comex",
                )
            )

        return out