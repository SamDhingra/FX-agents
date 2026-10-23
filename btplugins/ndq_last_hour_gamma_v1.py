from fxagents.bt import Strategy, Signal, Exits, Costs, ind
import numpy as np


class NdqLastHourGammaV1(Strategy):
    name = "ndq_last_hour_gamma_v1"
    symbol = "NDQ"
    description = (
        "Gao-Han-Li-Zhou / Baltussen last-hour intraday momentum on NDQ (14:30->15:55 NY) "
        "when 09:30-10:00 and 10:00-14:30 NY agree in sign and session displacement >= 0.80x 10d mean."
    )
    params = {
        "lookback_days": 10,
        "disp_ratio_min": 0.80,
        "r1_min_atr": 0.50,
        "pullback_max": 0.35,
        "atr_n": 14,
        "stop_atr": 1.20,
        "target_r": 1.75,
        "max_spread_frac": 0.08,
    }
    exits = Exits(target_r=1.75, flat_at=955, hold_overnight=False)
    entry_windows = [(870, 900)]  # 14:30 - 15:00 NY
    max_per_day = 1
    one_at_a_time = True
    news_block = (15, 15)
    warmup_days = 90
    variants = {
        "no_bimodal_agreement": {"r1_min_atr": -999.0},
        "no_magnitude_filter": {"disp_ratio_min": 0.0},
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

        lookback_days = int(self.p("lookback_days"))
        disp_ratio_min = float(self.p("disp_ratio_min"))
        r1_min_atr = float(self.p("r1_min_atr"))
        pullback_max = float(self.p("pullback_max"))
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
        disp_history = []
        out = []

        for i in range(max(atr_n + 2, 25), len(b)):
            t_start = int(b_start[i])
            t_end = int(b_end[i])
            m_idx_start = int(m.minute_at(t_start))
            if m_idx_start >= n_min:
                continue

            # 14:15 -> 14:30 NY bar has start minute-of-day == 855
            if int(m.mod[m_idx_start]) != 855:
                continue

            curr_day = int(m.day[m_idx_start])

            # Scan backward within the same NY day to find 09:30 open (mod 570) and 10:00 close (mod 585)
            idx_0930 = -1
            idx_0945 = -1
            for k in range(i - 1, max(-1, i - 25), -1):
                mk = int(m.minute_at(int(b_start[k])))
                if mk >= n_min or int(m.day[mk]) != curr_day:
                    break
                mod_k = int(m.mod[mk])
                if mod_k == 585:
                    idx_0945 = k
                elif mod_k == 570:
                    idx_0930 = k
                    break

            if idx_0930 < 0 or idx_0945 < 0:
                continue

            o_0930 = float(b_o[idx_0930])
            c_1000 = float(b_c[idx_0945])
            c_1430 = float(b_c[i])

            curr_disp = abs(c_1430 - o_0930)
            if len(disp_history) < lookback_days:
                disp_history.append(curr_disp)
                continue

            mean_disp_10 = float(np.mean(disp_history[-lookback_days:]))
            disp_history.append(curr_disp)

            if mean_disp_10 <= 1e-9:
                continue

            if (curr_disp / mean_disp_10) < disp_ratio_min:
                continue

            atr_val = float(np.mean(tr15[i - atr_n + 1 : i + 1]))
            if not np.isfinite(atr_val) or atr_val <= 0.0:
                continue

            r1 = c_1000 - o_0930
            r2 = c_1430 - c_1000

            cash_h = float(np.max(b_h[idx_0930 : i + 1]))
            cash_l = float(np.min(b_l[idx_0930 : i + 1]))
            cash_rng = cash_h - cash_l
            if cash_rng <= 1e-9:
                continue

            side = 0
            if r1_min_atr < 0.0:
                # Control variant without bimodal sign agreement
                if c_1430 > o_0930 and (cash_h - c_1430) / cash_rng <= pullback_max:
                    side = 1
                elif c_1430 < o_0930 and (c_1430 - cash_l) / cash_rng <= pullback_max:
                    side = -1
            else:
                if (
                    r1 > 0.0
                    and r2 > 0.0
                    and (r1 / atr_val) >= r1_min_atr
                    and (cash_h - c_1430) / cash_rng <= pullback_max
                ):
                    side = 1
                elif (
                    r1 < 0.0
                    and r2 < 0.0
                    and (abs(r1) / atr_val) >= r1_min_atr
                    and (c_1430 - cash_l) / cash_rng <= pullback_max
                ):
                    side = -1

            if side == 0:
                continue

            stop_dist = stop_atr * atr_val
            m_idx_last = min(n_min - 1, max(m_idx_start, int(m.minute_at(t_end)) - 1))
            curr_spread = float(m.spread[m_idx_last])
            if curr_spread * 1.3 > max_spread_frac * stop_dist:
                continue

            stop_price = round(float(c_1430 - side * stop_dist), 4)
            target_price = round(float(c_1430 + side * target_r * stop_dist), 4)

            out.append(
                Signal(
                    t=t_end,
                    side=side,
                    stop=stop_price,
                    target=target_price,
                    tag="ndq_last_hour_gamma",
                )
            )

        return out