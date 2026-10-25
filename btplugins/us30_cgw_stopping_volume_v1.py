from fxagents.bt import Strategy, Signal, Exits, Costs, ind
import numpy as np


class Us30CgwStoppingVolumeV1(Strategy):
    name = "us30_cgw_stopping_volume_v1"
    symbol = "US30"
    description = (
        "Campbell-Grossman-Wang (1993) stopping-volume reversal on US30: fades 1-hour "
        "directional stretches (>= 1.5 ATR) when 15m diurnal tick volume >= 1.5x 10d mean "
        "and the bar closes >= 45% off its extreme."
    )
    params = {
        "vol_days": 10,
        "vol_ratio_min": 1.50,
        "stretch_atr": 1.50,
        "reject_min": 0.45,
        "atr_n": 14,
        "stop_atr": 1.40,
        "target_r": 1.6,
        "max_spread_frac": 0.08,
    }
    exits = Exits(target_r=1.6, flat_at=950, hold_overnight=False)
    entry_windows = [(585, 885)]  # 09:45 - 14:45 NY
    max_per_day = 1
    one_at_a_time = True
    news_block = (15, 15)
    warmup_days = 90
    variants = {
        "no_volume_climax": {"vol_ratio_min": 0.0},
        "no_absorption_filter": {"reject_min": 0.0},
    }

    def signals(self, m):
        b = m.bars(15)
        if len(b) < 60:
            return []

        b_o = np.asarray(b.o, dtype=float)
        b_h = np.asarray(b.h, dtype=float)
        b_l = np.asarray(b.l, dtype=float)
        b_c = np.asarray(b.c, dtype=float)
        b_v = np.asarray(b.v, dtype=float)
        b_start = np.asarray(b.start, dtype=np.int64)
        b_end = np.asarray(b.end, dtype=np.int64)

        vol_days = int(self.p("vol_days"))
        vol_ratio_min = float(self.p("vol_ratio_min"))
        stretch_atr = float(self.p("stretch_atr"))
        reject_min = float(self.p("reject_min"))
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
        slot_vol_hist = {}
        out = []

        for i in range(max(atr_n + 4, 30), len(b)):
            t_start = int(b_start[i])
            t_end = int(b_end[i])
            m_idx_start = int(m.minute_at(t_start))
            if m_idx_start >= n_min:
                continue

            mod_start = int(m.mod[m_idx_start])
            if mod_start < 570 or mod_start > 855:
                continue

            curr_vol = float(b_v[i])
            hist = slot_vol_hist.get(mod_start)
            if hist is None:
                slot_vol_hist[mod_start] = [curr_vol]
                continue

            if len(hist) < vol_days:
                hist.append(curr_vol)
                continue

            mean_slot_vol = float(np.mean(hist[-vol_days:]))
            hist.append(curr_vol)
            if len(hist) > vol_days * 2:
                del hist[:-vol_days]

            if mean_slot_vol <= 0.0:
                continue

            # Condition 1: Diurnally-matched tick-volume climax
            vol_ratio = curr_vol / mean_slot_vol
            if vol_ratio < vol_ratio_min:
                continue

            atr_val = float(np.mean(tr15[i - atr_n + 1 : i + 1]))
            if not np.isfinite(atr_val) or atr_val <= 0.0:
                continue

            bar_rng = float(b_h[i] - b_l[i])
            if bar_rng <= 1e-9:
                continue

            # Conditions 2 & 3: 1-hour directional stretch + intrabar stopping-volume absorption
            prior_low_3 = float(np.min(b_l[i - 3 : i]))
            prior_high_3 = float(np.max(b_h[i - 3 : i]))

            up_stretch = float(b_h[i]) - prior_low_3
            dn_stretch = prior_high_3 - float(b_l[i])

            upper_reject = (float(b_h[i]) - float(b_c[i])) / bar_rng
            lower_reject = (float(b_c[i]) - float(b_l[i])) / bar_rng

            side = 0
            if (
                b_h[i] >= b_h[i - 1]
                and b_c[i] > b_o[i - 3]
                and up_stretch >= stretch_atr * atr_val
                and upper_reject >= reject_min
            ):
                side = -1
            elif (
                b_l[i] <= b_l[i - 1]
                and b_c[i] < b_o[i - 3]
                and dn_stretch >= stretch_atr * atr_val
                and lower_reject >= reject_min
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
                    tag="us30_cgw_stop_vol",
                )
            )

        return out