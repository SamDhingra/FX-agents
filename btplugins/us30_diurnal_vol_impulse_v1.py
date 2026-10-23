from fxagents.bt import Strategy, Signal, Exits, Costs, ind
import numpy as np


class Us30DiurnalVolImpulseV1(Strategy):
    name = "us30_diurnal_vol_impulse_v1"
    symbol = "US30"
    description = (
        "Enters US30 at 10:30 NY when 09:30-10:30 NY realized volatility expands "
        ">= 1.20x its trailing 10-day diurnal mean with first-hour efficiency >= 0.50."
    )
    params = {
        "rv_days": 10,
        "rv_ratio_min": 1.20,
        "rv_ratio_max": 3.00,
        "er_min": 0.50,
        "close_loc_min": 0.75,
        "atr_n": 14,
        "stop_atr": 1.25,
        "target_r": 2.0,
        "max_spread_frac": 0.08,
    }
    exits = Exits(target_r=2.0, flat_at=945, hold_overnight=False)
    entry_windows = [(630, 660)]  # 10:30 - 11:00 NY
    max_per_day = 1
    one_at_a_time = True
    news_block = (15, 15)
    warmup_days = 90
    variants = {
        "no_diurnal_vol_filter": {"rv_ratio_min": 0.0},
        "no_efficiency_filter": {"er_min": 0.0},
    }

    def signals(self, m):
        b = m.bars(15)
        if len(b) < 60:
            return []

        b_o = np.asarray(b.o, dtype=float)
        b_h = np.asarray(b.h, dtype=float)
        b_l = np.asarray(b.l, dtype=float)
        b_c = np.asarray(b.c, dtype=float)
        b_start = np.asarray(b.start, dtype=np.int64)
        b_end = np.asarray(b.end, dtype=np.int64)

        rv_days = int(self.p("rv_days"))
        rv_ratio_min = float(self.p("rv_ratio_min"))
        rv_ratio_max = float(self.p("rv_ratio_max"))
        er_min = float(self.p("er_min"))
        close_loc_min = float(self.p("close_loc_min"))
        atr_n = int(self.p("atr_n"))
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
        open_rv_history = []
        out = []

        for i in range(max(atr_n + 4, 20), len(b)):
            t_start = int(b_start[i])
            t_end = int(b_end[i])
            m_idx_start = int(m.minute_at(t_start))
            if m_idx_start >= n_min:
                continue

            # Evaluate at the 10:15 -> 10:30 NY bar (start mod == 615)
            if int(m.mod[m_idx_start]) != 615:
                continue

            curr_day = int(m.day[m_idx_start])

            # Verify bars i-3, i-2, i-1, i are the exact 4 bars of 09:30 -> 10:30 NY
            m0 = int(m.minute_at(int(b_start[i - 3])))
            m1 = int(m.minute_at(int(b_start[i - 2])))
            m2 = int(m.minute_at(int(b_start[i - 1])))
            if (
                m0 >= n_min
                or m1 >= n_min
                or m2 >= n_min
                or int(m.day[m0]) != curr_day
                or int(m.mod[m0]) != 570
                or int(m.mod[m1]) != 585
                or int(m.mod[m2]) != 600
            ):
                continue

            curr_open_rv = float(np.sum(tr15[i - 3 : i + 1]))
            if not np.isfinite(curr_open_rv) or curr_open_rv <= 0.0:
                continue

            if len(open_rv_history) < rv_days:
                open_rv_history.append(curr_open_rv)
                continue

            trailing_rv_mean = float(np.mean(open_rv_history[-rv_days:]))
            open_rv_history.append(curr_open_rv)

            if trailing_rv_mean <= 0.0:
                continue

            rv_ratio = curr_open_rv / trailing_rv_mean
            if rv_ratio < rv_ratio_min or rv_ratio > rv_ratio_max:
                continue

            # 4-bar first-hour efficiency ratio
            net_move = float(b_c[i] - b_o[i - 3])
            step_path = (
                abs(float(b_c[i - 3] - b_o[i - 3]))
                + abs(float(b_c[i - 2] - b_c[i - 3]))
                + abs(float(b_c[i - 1] - b_c[i - 2]))
                + abs(float(b_c[i] - b_c[i - 1]))
            )
            if step_path <= 1e-9:
                continue

            er_1h = abs(net_move) / step_path
            if er_1h < er_min:
                continue

            h_1h = float(np.max(b_h[i - 3 : i + 1]))
            l_1h = float(np.min(b_l[i - 3 : i + 1]))
            rng_1h = h_1h - l_1h
            if rng_1h <= 1e-9:
                continue

            side = 0
            if net_move > 0.0 and (float(b_c[i]) - l_1h) / rng_1h >= close_loc_min:
                side = 1
            elif net_move < 0.0 and (h_1h - float(b_c[i])) / rng_1h >= close_loc_min:
                side = -1

            if side == 0:
                continue

            atr_val = float(np.mean(tr15[i - atr_n + 1 : i + 1]))
            if not np.isfinite(atr_val) or atr_val <= 0.0:
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
                    tag="us30_diurnal_vol_imp",
                )
            )

        return out