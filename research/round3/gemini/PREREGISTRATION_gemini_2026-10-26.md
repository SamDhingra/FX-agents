### A. Pre-Registered "What-If" Skip Checks (4 Proposals)

The four checks already running (`m15_live`, `m15_closed`, `m15_trend`, `h1_live`) test single-candle direction and a slow 20-bar EMA slope. A discretionary trader watching 3m/5m signals against the 15m/1H chart looks for four specific structural failure modes that those checks miss:

#### 1. `m15_impulse_leg` — Stepping in front of an active 15m counter-impulse
* **Failure mode removed:** `m15_closed` flags *any* opposing 15m candle, including harmless 1-bar inside pauses where discount/OTE entries are supposed to work. What actually destroys a 3m/5m entry is when the 15m is in an **active counter-trend impulse leg**—either two consecutive 15m candles stair-stepping against the trade, or a wide-range 15m counter-displacement bar that closes on its extreme.
* **Exact condition:** (See `m15_impulse_leg.py`)
* **Fixed parameter rationale:** `2` bars is the minimum multi-bar impulse leg; `0.75` ATR(14) body and `0.25` (quartile close) are standard institutional definitions of an unexhausted wide-range expansion bar.

#### 2. `ltf_swing_structure_against` — Active 5m Dow-structure staircase progressing against the trade
* **Failure mode removed:** `m15_trend` uses a 20-bar 15m EMA (5 hours of lag), which stays aligned with the old bias long after a 30-to-90 minute counter-trend wave has taken control. A human chart watcher looks at the last 2–3 hours of 5m structure: if confirmed 5m swing highs *and* confirmed 5m swing lows are both stair-stepping against the trade and price is still on the wrong side of the 1-hour mean (`EMA_5m(12)`), the pullback has not broken structure yet.
* **Exact condition:** (See `ltf_swing_structure_against.py`)
* **Fixed parameter rationale:** `2` bars (10 minutes on 5m) is the fastest look-ahead-safe fractal confirmation that filters single-bar noise; `36` 5m bars = 3 hours (one intraday session block); `12` 5m bars = 1 hour.

#### 3. `stop_inside_15m_noise` — 3m/5m stop is smaller than ordinary 15m intrabar noise or spread-to-risk is lethal
* **Failure mode removed:** When a 3m/5m stop is narrower than half of a single 15m bar's average range ($0.50 \times \text{ATR}_{15}(14)$) or when the current 1-minute spread exceeds $8\%$ of the stop, ordinary 15m noise clips the stop before the HTF bias can play out.
* **Exact condition:** (See `stop_inside_15m_noise.py`)
* **Fixed parameter rationale:** `0.50` $\times \text{ATR}_{15}(14)$ is the expected one-sided excursion of a driftless 15m bar from its open; `0.08` ($8\%$) raw spread-to-stop is the cost boundary where $2\times$ costs exceed $0.20\text{R}$.

#### 4. `chasing_exhausted_leg` — Entering into the extreme of an un-retraced 60-minute expansion move in the trade's direction
* **Failure mode removed:** The mirror mistake of fighting a 15m counter-move is chasing an already-exhausted 15m move. When price has already traveled $\ge 2.0 \times \text{ATR}_{15}(14)$ in the trade's direction over the past 60 minutes and the 3m/5m bot fires right at the extreme (within $0.25 \times \text{ATR}_{15}(14)$ of the peak/trough), the 15m leg is due for mean reversion.
* **Exact condition:** (See `chasing_exhausted_leg.py`)
* **Fixed parameter rationale:** `60` minutes = four 15m bars; under diffusive scaling ($\sqrt{4} = 2$), a 4-bar move $\ge 2.0 \times \text{ATR}_{15}(14)$ still sitting within `0.25` $\text{ATR}_{15}$ of its peak represents an un-retraced 1-hour expansion leg.

---

### B. "Wait Instead of Skip" Delayed-Entry Rule (1 Proposal)

1. **Evaluate Immediate vs. Watchlist State at Signal Time $t_0$:** When a 3m or 5m playbook signal fires at $t_0$ with side $s \in \{+1, -1\}$, entry price $P_0 = \text{close}_{t_0}$, initial risk distance $R_0 = \text{risk\_atr} \times \text{ATR}_{\text{tf}}(14)$, and structural stop price $S_0 = P_0 - s \cdot R_0$, check whether the 15m candle in progress (`m15_live`) OR the last completed 15m candle (`m15_closed`) is opposing $s$. If neither is opposing $s$, execute the trade immediately at $t_0$. If either is opposing $s$, withhold execution and place the signal on watchlist for at most $N = 45\text{ minutes}$ ($t \in (t_0, t_0 + 45\text{ min}]$).
2. **Monitor 1-Minute Invalidation Conditions During $(t_0, t]$:** Step forward minute-by-minute through `m1`. Cancel the pending watchlist signal permanently if, on any 1-minute bar before a valid 15m turn candle closes:
   * **Stop Hit:** $\text{low}_t \le S_0$ (for $s = +1$) or $\text{high}_t \ge S_0$ (for $s = -1$); OR
   * **Missed Move ($X = 0.75 R_0$):** Price reaches $P_0 + s \cdot 0.75 R_0$ ($\text{high}_t \ge P_0 + 0.75 R_0$ for $s = +1$; $\text{low}_t \le P_0 - 0.75 R_0$ for $s = -1$); OR
   * **Timer Expired:** $t > t_0 + 45\text{ minutes}$.
3. **Check for 15m Turn Confirmation at Each 15m Boundary $t_{15} \in (t_0, t_0 + 45\text{ min}]$:** Whenever a 15m candle completes at $t_{15}$ (`minute` $\in \{0, 15, 30, 45\}$), check whether that completed 15m candle closed in the trade's direction: $s \cdot (C_{15\text{m}} - O_{15\text{m}}) > 0$. If not, continue waiting up to $t_0 + 45\text{ minutes}$.
4. **Validate Risk Geometry and Execution Gates at the 15m Turn Close $t_{\text{fill}} = t_{15}$:** On the first completed 15m candle where $s \cdot (C_{15\text{m}} - O_{15\text{m}}) > 0$, set the new entry price $P_{\text{new}} = C_{15\text{m}}$, keep the original stop price $S_{\text{new}} = S_0$, and compute the new risk distance $R_{\text{new}} = s \cdot (P_{\text{new}} - S_0)$. Cancel the signal if $R_{\text{new}} < 0.50 R_0$ (stop too close / micro-stop), if $R_{\text{new}} > 1.35 R_0$ (stop too wide), if $t_{\text{fill}}$ falls outside the bot's allowed `entry_windows` or inside `news_block`, or if $\text{spread}_{t_{\text{fill}}} > 0.08 R_{\text{new}}$.
5. **Execute Delayed Trade and Re-Index Live Management to $R_{\text{new}}$:** Enter at $t_{\text{fill}}$ at price $P_{\text{new}}$ with stop $S_0$. Run the bot's exact live trade management from $t_{\text{fill}}$ onward with $1\text{R} \equiv R_{\text{new}}$ (bank 50% partial at $P_{\text{new}} + s \cdot 1.0 R_{\text{new}}$, move stop to $P_{\text{new}} + s \cdot 0.1 R_{\text{new}}$, trail in $+1.0 R_{\text{new}}$ steps, and apply the 45-minute stall rule from $t_{\text{fill}}$).

---

### C. Mechanistic Read & Literature (Why Entering Against the Active HTF Bar Loses)

* **Institutional Parent-Order Slicing (Microstructure Mechanism):** Institutional execution algorithms (VWAP, TWAP, POV) slice parent orders across 15-to-60 minute intervals. When a 15m candle is actively expanding against your trade, a 3m/5m "reversal setup" (MSS, CISD, wick fib) is almost always a 1-to-3 minute pause between child-order slices of an active 15m parent order—not the end of the institutional flow.
* **First-Passage Time Asymmetry Under Short-Horizon Drift:** When the 15m bar has an active opposing drift $\mu_{15}$ and your 3m/5m stop is only $0.35\text{–}0.60 \times \text{ATR}_{15}$ away, the Brownian first-passage probability of hitting the stop inside the next 15 minutes exceeds $65\%$. 
* **Known Literature & Terminology:** In academic econometrics, this is **Cross-Scale Order-Flow Autocorrelation / Heterogeneous Autoregressive (HAR) Volatility**. In trading literature, it is **Alexander Elder's (1986) "Triple Screen"** rule, **Al Brooks' "First Break of a Micro-Channel"**, and in ICT/SMC terminology **"Entering during the HTF Judas Swing / Manipulation Leg before HTF Distribution"**.
* **When is the opposite true (when does fading into an opposing 15m pullback work)?** Buying a falling 15m candle works **only when two conditions hold simultaneously**: (1) the 15m pullback is **decelerating into an HTF liquidity/value zone** after already retracing $\sim 50\%\text{–}70\%$ of the prior 1H impulse, **and** (2) the **stop is sized to the 15m/1H structure** ($\ge 1.2\text{–}1.5 \times \text{ATR}_{15}$).
* **Why the Playbook's OTE / Discount / Fib Rules Failed:** They pair a **15m/1H mean-reversion premise with a 3m/5m stop width** and then cap winners via `"bank 50% at 1R, stop to +0.1R"`. They get stopped out by normal 15m continuation noise when early, and harvest only a fraction of a 15m bar when right, leaving full $-1\text{R}$ losses intact.

---

### D. Honest Priors (Passing Seen Data + 2016–2020 Vault)

* **Probability of passing the Check Gates (`kept - flagged > 0` in 95% bootstrap, both halves, $p < 0.05$ vs random skip, on Seen AND 2016–2020):**
  1. **`stop_inside_15m_noise` — 35% chance:** Directly targets the mathematical cost/noise floor.
  2. **`m15_impulse_leg` — 28% chance:** Isolates multi-bar 15m counter-staircases and wide-range 15m counter-marubozus (~18%–25% of trades) where short-horizon continuation against the entry is strongest.
  3. **`ltf_swing_structure_against` — 22% chance:** Captures 30-to-90 minute counter-trend 5m staircases that `m15_live` and `m15_trend` miss.
  4. **`chasing_exhausted_leg` — 18% chance:** Flags late continuation entries at the extreme of a $\ge 2.0\,\text{ATR}_{15}$ 60-minute spike (~12%–18% of trades).
  5. **Section B Delayed-Entry Rule (`wait_for_m15_turn`) — 20% chance of beating immediate entry, < 8% chance of making the playbook $> 0\text{R}$ net.**
* **Can ANY of these filters turn the $-0.09\text{R}$ playbook positive ($> 0\text{R}$ after costs)? Plainly: No (< 5% probability).**
  To bring the kept $70\%$ to a viable **$\bar{R}_{\text{kept}} = +0.08\text{R}$**, the flagged $30\%$ would have to average **$-0.49\text{R}$ per trade**. If a check flags $30\%$ of trades and those flagged trades average $-0.16\text{R}$, the kept $70\%$ improves from $-0.09\text{R}$ to **$-0.06\text{R}$**—which passes the check gates but **still loses money after costs**.