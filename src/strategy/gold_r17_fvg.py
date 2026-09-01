"""R17 — FVG (Fair Value Gap), XAU/USD spot.

Hypothesis (docs/research/R15_R17_SMC_PLAN.md, R17):
  A 3-candle price gap (bar i's low clears bar i-2's high with no overlap,
  or the mirror for a bearish gap) marks a level with no two-way trading —
  claimed to act as a magnet the market tends to revisit and (partially)
  fill. Distinct from R11 (wick-fill: intra-candle rejection on a SINGLE
  bar) — this is an inter-candle 3-bar gap with zero overlap. Mechanism is
  the weakest of the three SMC hypotheses in this track (no forced-stop
  argument like CHoCH/OB) — see plan §2 for why. Mandatory baselines: R11
  (same "fade an imbalance" family) and plain mean-reversion (see plan §7).

Bullish FVG at bar i:  low[i] > high[i-2]  -> zone [high[i-2], low[i]]
Bearish FVG at bar i:  high[i] < low[i-2]  -> zone [high[i], low[i-2]]
gap_size filter: zone height >= k_gap * ATR[i] (screens out noise-sized gaps)

Only ONE pending (unconsumed) gap per direction is tracked at a time; a new
gap of the same direction overwrites the old one (same "most recent takes
precedence" convention as R14's active pivot level). A gap is consumed
(removed from tracking) either when its retest is resolved (trade fired or
rejected because price closed through it) or when the N-bar timeout expires
without a retest.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HIGH_LIQ_HOURS = range(8, 21)  # LONDON(8-13) + OVERLAP(13-16) + NY(16-21) UTC


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def generate_r17_signals(
    m15: pd.DataFrame,
    atr_len: int = 14,
    k_gap: float = 0.5,
    N: int = 10,
    buf: float = 0.1,
    tp_r_mult: float = 1.5,
    direction: str = "both",       # "both" | "long"
    session_filter: bool = True,
) -> pd.DataFrame:
    df = m15[["time_utc", "open", "high", "low", "close"]].copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)
    df["atr"] = _atr(df, atr_len)
    df["hour"] = df["time_utc"].dt.hour

    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    atr = df["atr"].to_numpy()
    hour = df["hour"].to_numpy()
    t = df["time_utc"].to_numpy()
    n = len(df)

    allow_long = direction in ("both", "long")
    allow_short = direction in ("both",)

    rows = []
    next_allowed = 0

    # active bullish gap: zone [bull_low, bull_high] = [high[i-2], low[i]], formed at bull_i
    bull_low = bull_high = np.nan
    bull_formed = -1
    # active bearish gap: zone [bear_low, bear_high] = [high[i], low[i-2]], formed at bear_i
    bear_low = bear_high = np.nan
    bear_formed = -1

    for i in range(n):
        a = atr[i]
        atr_ok = a > 0 and not np.isnan(a)

        # -------- detect new gaps formed AT this bar (uses i-2, no look-ahead) --------
        if i >= 2 and atr_ok:
            if l[i] > h[i - 2] and (l[i] - h[i - 2]) >= k_gap * a:
                bull_low, bull_high, bull_formed = h[i - 2], l[i], i
            if h[i] < l[i - 2] and (l[i - 2] - h[i]) >= k_gap * a:
                bear_low, bear_high, bear_formed = h[i], l[i - 2], i

        if i < next_allowed or not atr_ok:
            continue

        fired = False
        session_ok = (not session_filter) or (hour[i] in HIGH_LIQ_HOURS)

        # -------- bullish gap: retest from above, then LONG --------
        if allow_long and bull_formed >= 0 and i > bull_formed:
            bars_since = i - bull_formed
            if bars_since > N:
                bull_formed = -1  # timeout, consumed unfilled
            elif l[i] <= bull_high:
                # retest touched the gap's upper edge
                if c[i] > bull_low and session_ok:
                    sl_price = bull_low - buf * a
                    sl_d = c[i] - sl_price
                    if sl_d > 0:
                        tp_price = c[i] + tp_r_mult * sl_d
                        rows.append((t[i], c[i], "LONG", sl_price, tp_price, sl_d))
                        next_allowed = i + 1
                        fired = True
                bull_formed = -1  # consumed either way (traded or gap fully filled through)

        if fired:
            continue

        # -------- bearish gap: retest from below, then SHORT --------
        if allow_short and bear_formed >= 0 and i > bear_formed:
            bars_since = i - bear_formed
            if bars_since > N:
                bear_formed = -1
            elif h[i] >= bear_low:
                if c[i] < bear_high and session_ok:
                    sl_price = bear_high + buf * a
                    sl_d = sl_price - c[i]
                    if sl_d > 0:
                        tp_price = c[i] - tp_r_mult * sl_d
                        rows.append((t[i], c[i], "SHORT", sl_price, tp_price, sl_d))
                        next_allowed = i + 1
                bear_formed = -1

    cols = ["time_utc", "close", "action", "sl_price", "tp_price", "sl_distance"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)
