from fxagents.bt import Strategy, Signal, Exits, Costs, ind
import numpy as np


class NdqPdhlAdrBreakoutV1(Strategy):
    name = "ndq_pdhl_adr_breakout_v1"
    symbol = "NDQ"
    description = (
        "Trades 15m acceptance breakouts of Prior Day High/Low (PDH/PDL) on NDQ "
        "when session range is <= 65% of 14-day ADR and aligned with 4H EMA(20)."
    )
    params = {
        "adr_n": 14,
        "adr_max_frac": 0.65,
        "ema_h4_n": 20,
        "max_break_atr": 1.0,
        "atr_n": 14,
        "stop_atr": 1.50,
        "target_r": 1.8,
        "use_ema": 1,
        "max_spread_frac": 0.08,
    }
    exits = Exits(target_r=1.8, flat_at=950, hold_overnight=False)
    entry_windows = [(510, 840)]  # 08:30 - 14:00 NY
    max_per_day = 1
    one_at_a_time = True
    news_block = (15, 15)
    warmup_days = 120
    variants = {
        "no_adr_filter": {"adr_max_frac": 9.99},
        "no_ema_filter": {"use_ema": 0},
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

    def signals(self, m):
        b = m.bars(15)
        h4 = m.bars("4h")
        d = m.bars("1d")
        if len(b) < 60 or len(h4) < 30 or len(d) < 25:
            return []

        b_o = np.asarray(b.o, dtype=float)
        b_h = np.asarray(b.h, dtype=float)
        b_l = np.asarray(b.l, dtype=float)
        b_c = np.asarray(b.c, dtype=float)
        b_start = np.asarray(b.start, dtype=np.int64)
        b_end = np.asarray(b.end, dtype=np.int64)

        h4_c = np.asarray(h4.c, dtype=float)
        d_h = np.asarray(d.h, dtype=float)
        d_l = np.asarray(d.l, dtype=float)
        d_rng = d_h - d_l

        adr_n = int(self.p("adr_n"))
        adr_max_frac = float(self.p("adr_max_frac"))
        ema_h4_n = int(self.p("ema_h4_n"))
        max_break_atr = float(self.p("max_break_atr"))
        atr_n = int(self.p("atr_n"))
        stop_atr = float(self.p("stop_atr"))
        target_r = float(self.p("target_r"))
        use_ema = int(self.p("use_ema"))
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

        for i in range(max(atr_n + 4, 40), len(b)):
            t_start = int(b_start[i])
            t_end = int(b_end[i])
            m_idx_start = int(m.minute_at(t_start))
            if m_idx_start >= n_min:
                continue

            # 15m bars closing in [08:30, 14:00] NY have start mod in [495, 825]
            mod_start = int(m.mod[m_idx_start])
            if mod_start < 495 or mod_start > 825:
                continue

            d_idx = int(m.last_closed("1d", t_end))
            if d_idx < adr_n + 5:
                continue

            # Collect last adr_n valid full daily bars (skip brief holiday/Sunday stubs)
            ref_med = float(np.median(d_rng[max(0, d_idx - 25) : d_idx + 1]))
            valid_idx = []
            for k in range(d_idx, -1, -1):
                if d_rng[k] >= 0.20 * ref_med and d_rng[k] > 0.0:
                    valid_idx.append(k)
                    if len(valid_idx) == adr_n:
                        break
            if len(valid_idx) < adr_n:
                continue

            pd_idx = valid_idx[0]
            pdh = float(d_h[pd_idx])
            pdl = float(d_l[pd_idx])
            adr_val = float(np.mean([d_rng[k] for k in valid_idx]))
            if not np.isfinite(adr_val) or adr_val <= 0.0:
                continue

            atr_val = float(np.mean(tr15[i - atr_n + 1 : i + 1]))
            if not np.isfinite(atr_val) or atr_val <= 0.0:
                continue

            # Condition 1: 15m acceptance close across PDH or PDL
            side = 0
            if (
                b_c[i] > pdh
                and b_c[i - 1] <= pdh
                and b_c[i] > b_o[i]
                and (b_c[i] - pdh) <= max_break_atr * atr_val
            ):
                side = 1
            elif (
                b_c[i] < pdl
                and b_c[i - 1] >= pdl
                and b_c[i] < b_o[i]
                and (pdl - b_c[i]) <= max_break_atr * atr_val
            ):
                side = -1

            if side == 0:
                continue

            # Condition 2: Current trading session range <= adr_max_frac * ADR(14)
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
            if (sess_range / adr_val) > adr_max_frac:
                continue

            # Condition 3: 4H EMA(20) trend alignment
            if use_ema == 1:
                h4_idx = int(m.last_closed("4h", t_end))
                if h4_idx < ema_h4_n:
                    continue
                ema_h4 = self._finite_ema(h4_c, h4_idx, ema_h4_n)
                if side == 1 and b_c[i] <= ema_h4:
                    continue
                if side == -1 and b_c[i] >= ema_h4:
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
                    tag="ndq_pdhl_adr_brk",
                )
            )

        return out