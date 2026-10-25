from fxagents.bt import Strategy, Signal, Exits, Costs, ind
import numpy as np


class Us30AdrExhaustionFadeV1(Strategy):
    name = "us30_adr_exhaustion_fade_v1"
    symbol = "US30"
    description = (
        "Fades US30 intraday extensions during 09:45-14:30 NY when session range reaches "
        "85%-160% of 14-day ADR, stretches >= 0.50 ADR from PDC, and 15m RSI(7) hooks."
    )
    params = {
        "adr_n": 14,
        "adr_min_frac": 0.85,
        "adr_max_frac": 1.60,
        "pdc_band_frac": 0.50,
        "rsi_n": 7,
        "rsi_win": 35,
        "rsi_ob": 70.0,
        "rsi_os": 30.0,
        "atr_n": 14,
        "stop_atr": 1.40,
        "target_r": 1.5,
        "max_spread_frac": 0.08,
    }
    exits = Exits(target_r=1.5, flat_at=950, hold_overnight=False)
    entry_windows = [(585, 885)]  # 09:45 - 14:45 NY
    max_per_day = 1
    one_at_a_time = True
    news_block = (15, 15)
    warmup_days = 120
    variants = {
        "no_adr_exhaustion": {"adr_min_frac": 0.30},
        "no_rsi_filter": {"rsi_ob": 50.0, "rsi_os": 50.0},
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
        if len(b) < 60 or len(d) < 25:
            return []

        b_o = np.asarray(b.o, dtype=float)
        b_h = np.asarray(b.h, dtype=float)
        b_l = np.asarray(b.l, dtype=float)
        b_c = np.asarray(b.c, dtype=float)
        b_start = np.asarray(b.start, dtype=np.int64)
        b_end = np.asarray(b.end, dtype=np.int64)

        d_h = np.asarray(d.h, dtype=float)
        d_l = np.asarray(d.l, dtype=float)
        d_c = np.asarray(d.c, dtype=float)
        d_rng = d_h - d_l

        adr_n = int(self.p("adr_n"))
        adr_min_frac = float(self.p("adr_min_frac"))
        adr_max_frac = float(self.p("adr_max_frac"))
        pdc_band_frac = float(self.p("pdc_band_frac"))
        rsi_n = int(self.p("rsi_n"))
        rsi_win = int(self.p("rsi_win"))
        rsi_ob = float(self.p("rsi_ob"))
        rsi_os = float(self.p("rsi_os"))
        atr_n = int(self.p("atr_n"))
        stop_atr = float(self.p("stop_atr"))
        target_r = float(self.p("target_r"))
        max_spread_frac = float(self.p("max_spread_frac"))

        tr15 = np.empty(len(b), dtype=float)
        tr15[0] = b_h[0] - b_l[0]
        for i in range(1, len(b)):
            tr15[i] = max(
                b_h[i] - b_l[i],
                abs(b_h[i] - b_c[i - 1]),
                abs(b_l[i] - b_c[i - 1]),
            )

        n_min = len(m.ns)
        out = []

        for i in range(max(atr_n + 4, rsi_win + 2), len(b)):
            t_start = int(b_start[i])
            t_end = int(b_end[i])
            m_idx_start = int(m.minute_at(t_start))
            if m_idx_start >= n_min:
                continue

            # 15m bars closing in [09:45, 14:30] NY have start mod in [570, 855]
            mod_start = int(m.mod[m_idx_start])
            if mod_start < 570 or mod_start > 855:
                continue

            d_idx = int(m.last_closed("1d", t_end))
            if d_idx < adr_n + 5:
                continue

            ref_med = float(np.median(d_rng[max(0, d_idx - 25) : d_idx + 1]))
            valid_idx = []
            for k in range(d_idx, -1, -1):
                if d_rng[k] >= 0.20 * ref_med and d_rng[k] > 0.0:
                    valid_idx.append(k)
                    if len(valid_idx) == adr_n:
                        break
            if len(valid_idx) < adr_n:
                continue

            pdc = float(d_c[valid_idx[0]])
            adr_val = float(np.mean([d_rng[k] for k in valid_idx]))
            if not np.isfinite(adr_val) or adr_val <= 0.0:
                continue

            atr_val = float(np.mean(tr15[i - atr_n + 1 : i + 1]))
            if not np.isfinite(atr_val) or atr_val <= 0.0:
                continue

            # Current trading session range since 18:00 NY
            curr_sess = int(m.sess[m_idx_start])
            sess_high = float(b_h[i])
            sess_low = float(b_l[i])
            for k in range(i - 1, max(-1, i - 80), -1):
                mk = int(m.minute_at(int(b_start[k])))
                if mk < n_min and int(m.sess[mk]) == curr_sess:
                    if b_h[k] > sess_high:
                        sess_high = float(b_h[k])
                    if b_l[k] < sess_low:
                        sess_low = float(b_l[k])
                else:
                    break

            sess_range = sess_high - sess_low
            adr_used = sess_range / adr_val

            # Condition 1: ADR exhaustion bounds
            if adr_used < adr_min_frac or adr_used > adr_max_frac:
                continue

            rsi_curr = self._finite_wilder_rsi(b_c, i, rsi_n, rsi_win)
            rsi_prev = self._finite_wilder_rsi(b_c, i - 1, rsi_n, rsi_win)

            # Conditions 1b, 2, and 3: Session extreme + PDC band stretch + RSI(7) turn
            side = 0
            recent_hi = max(float(b_h[i - 1]), float(b_h[i]))
            recent_lo = min(float(b_l[i - 1]), float(b_l[i]))

            if (
                recent_hi >= sess_high - 0.15 * atr_val
                and sess_high >= pdc + pdc_band_frac * adr_val
                and max(rsi_prev, rsi_curr) >= rsi_ob
                and b_c[i] < b_o[i]
            ):
                side = -1
            elif (
                recent_lo <= sess_low + 0.15 * atr_val
                and sess_low <= pdc - pdc_band_frac * adr_val
                and min(rsi_prev, rsi_curr) <= rsi_os
                and b_c[i] > b_o[i]
            ):
                side = 1

            if side == 0:
                continue

            stop_dist = stop_atr * atr_val
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
                    tag="us30_adr_exh_fade",
                )
            )

        return out