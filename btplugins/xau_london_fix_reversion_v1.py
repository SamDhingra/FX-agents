from fxagents.bt import Strategy, Signal, Exits, Costs, ind
import numpy as np


class XauLondonFixReversionV1(Strategy):
    name = "xau_london_fix_reversion_v1"
    symbol = "XAUUSD"
    description = (
        "Fades overextended 03:00->10:30 NY London-to-LBMA-PM-Fix directional moves "
        "on XAUUSD when the 10:00-10:30 NY fixing window prints a rejection wick."
    )
    params = {
        "atr_n": 14,
        "ext_min_atr": 2.5,
        "ext_max_atr": 6.0,
        "wick_min": 0.35,
        "stop_atr": 1.25,
        "target_r": 1.75,
        "max_spread_frac": 0.08,
    }
    exits = Exits(target_r=1.75, flat_at=930, hold_overnight=False)
    entry_windows = [(630, 660)]  # 10:30 - 11:00 NY
    max_per_day = 1
    one_at_a_time = True
    news_block = (30, 30)
    warmup_days = 90
    variants = {
        "no_extension_filter": {"ext_min_atr": 0.5},
        "no_rejection_filter": {"wick_min": 0.0},
    }

    def signals(self, m):
        b = m.bars(15)
        if len(b) < 50:
            return []

        b_o = np.asarray(b.o, dtype=float)
        b_h = np.asarray(b.h, dtype=float)
        b_l = np.asarray(b.l, dtype=float)
        b_c = np.asarray(b.c, dtype=float)
        b_start = np.asarray(b.start, dtype=np.int64)
        b_end = np.asarray(b.end, dtype=np.int64)

        atr_n = int(self.p("atr_n"))
        ext_min_atr = float(self.p("ext_min_atr"))
        ext_max_atr = float(self.p("ext_max_atr"))
        wick_min = float(self.p("wick_min"))
        stop_atr = float(self.p("stop_atr"))
        target_r = float(self.p("target_r"))
        max_spread_frac = float(self.p("max_spread_frac"))

        # Causal 15m True Range
        tr15 = np.empty(len(b), dtype=float)
        tr15[0] = b_h[0] - b_l[0]
        for i in range(1, len(b)):
            hl = b_h[i] - b_l[i]
            hc = abs(b_h[i] - b_c[i - 1])
            lc = abs(b_l[i] - b_c[i - 1])
            tr15[i] = max(hl, hc, lc)

        n_min = len(m.ns)
        out = []

        for i in range(max(atr_n + 2, 35), len(b)):
            t_start = int(b_start[i])
            t_end = int(b_end[i])
            m_idx_start = int(m.minute_at(t_start))
            if m_idx_start >= n_min:
                continue

            # 10:15 -> 10:30 NY bar has start minute-of-day == 615
            if int(m.mod[m_idx_start]) != 615:
                continue

            curr_day = int(m.day[m_idx_start])

            # Locate 03:00 -> 03:15 NY bar (start mod == 180) on the same NY calendar day
            lon_open_price = np.nan
            for k in range(i - 1, max(-1, i - 36), -1):
                mk = int(m.minute_at(int(b_start[k])))
                if mk >= n_min or int(m.day[mk]) != curr_day:
                    break
                if int(m.mod[mk]) == 180:
                    lon_open_price = float(b_o[k])
                    break

            if not np.isfinite(lon_open_price):
                continue

            # Verify previous bar is 10:00 -> 10:15 NY on the same day
            m_prev = int(m.minute_at(int(b_start[i - 1])))
            if m_prev >= n_min or int(m.day[m_prev]) != curr_day or int(m.mod[m_prev]) != 600:
                continue

            atr_val = float(np.mean(tr15[i - atr_n + 1 : i + 1]))
            if not np.isfinite(atr_val) or atr_val <= 0.0:
                continue

            delta_lon = float(b_c[i] - lon_open_price)
            abs_delta_atr = abs(delta_lon) / atr_val
            if abs_delta_atr < ext_min_atr or abs_delta_atr > ext_max_atr:
                continue

            fix_high = max(float(b_h[i - 1]), float(b_h[i]))
            fix_low = min(float(b_l[i - 1]), float(b_l[i]))
            fix_range = fix_high - fix_low
            if fix_range <= 1e-9:
                continue

            side = 0
            if delta_lon > 0.0:
                upper_rej = (fix_high - float(b_c[i])) / fix_range
                if upper_rej >= wick_min:
                    side = -1
            else:
                lower_rej = (float(b_c[i]) - fix_low) / fix_range
                if lower_rej >= wick_min:
                    side = 1

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
                    tag="xau_london_fix_rev",
                )
            )

        return out