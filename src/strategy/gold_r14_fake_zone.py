"""R14 — Level-Anchored Liquidity Sweep (fake breakout reversal), XAU/USD spot.

Hypothesis (docs/research/XAU_REDDIT_SCOUT.md, "รอบ Facebook" section, R14):
  Price sweeps past a structural swing level (pivot high/low), triggering
  breakout traders + clustered stops beyond the level, then FAILS to hold and
  closes back inside within N bars -> fade the sweep (short after a failed
  upside break, long after a failed downside break). Distinct from R11
  (wick-fill, any-bar wick shape, no level) and R8 (candle-fade, no level):
  R14 requires a level defined by a confirmed pivot fractal + a close-back
  confirmation bar.

On m15, per closed bar i (SHORT side; LONG mirrors):
  1. level = most recent CONFIRMED pivot high: bar p is a pivot high iff
     high[p] > high[p-w..p-1] and high[p] > high[p+1..p+w] (w bars each side).
     A pivot at index p is only KNOWN/confirmed at bar p+w (needs w bars of
     right-side confirmation) -> no look-ahead: we only reference a pivot
     once the current bar index >= p+w, and the pivot must not yet have been
     "used" (broken by an earlier close, i.e. still the active unbroken level).
  2. break: some bar j (p+w <= j <= i) has high[j] > level + b_break*ATR[j]
     (a genuine break beyond the level, not a tick touch). Track the sweep
     extreme = max(high) over the break window.
  3. fake confirm: bar i CLOSES back below level (close[i] < level), and i is
     within N bars of the first break bar j (i - j <= N-1, i.e. break+confirm
     happens within an N-bar window). THEN action=SHORT at close[i].
     sl_price    = sweep_extreme + buf*ATR[i]
     sl_distance = sl_price - close[i]  (>0)
     tp_price    = close[i] - tp_r_mult * sl_distance
  4. invalidate: if N bars pass after the break without a close back inside,
     the breakout is treated as real -> stand down, level is consumed
     (mark broken, do not keep fading a trending breakout).
  session: entry bar i must be in high_liquidity hours (LONDON/OVERLAP/NY).
  one-trade: no overlapping arms; a level is consumed (invalidated) once
  either a trade fires or the breakout is confirmed real.

LONG mirrors using pivot lows / low[] with signs flipped.
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


def _pivot_highs(high: np.ndarray, w: int) -> np.ndarray:
    """Boolean array: pivot_high[p] True iff high[p] is strictly > all highs
    within w bars on both sides. Vectorized via rolling-window comparison."""
    n = len(high)
    is_piv = np.ones(n, dtype=bool)
    for k in range(1, w + 1):
        left = np.full(n, -np.inf)
        left[k:] = high[:-k]
        right = np.full(n, -np.inf)
        right[:-k] = high[k:]
        is_piv &= (high > left) & (high > right)
    # edges without full w bars on both sides can't be confirmed pivots
    is_piv[:w] = False
    is_piv[n - w:] = False
    return is_piv


def _pivot_lows(low: np.ndarray, w: int) -> np.ndarray:
    n = len(low)
    is_piv = np.ones(n, dtype=bool)
    for k in range(1, w + 1):
        left = np.full(n, np.inf)
        left[k:] = low[:-k]
        right = np.full(n, np.inf)
        right[:-k] = low[k:]
        is_piv &= (low < left) & (low < right)
    is_piv[:w] = False
    is_piv[n - w:] = False
    return is_piv


def generate_r14_signals(
    m15: pd.DataFrame,
    atr_len: int = 14,
    w: int = 3,
    b_break: float = 0.5,
    N: int = 3,
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

    piv_high = _pivot_highs(h, w)
    piv_low = _pivot_lows(l, w)

    allow_short = direction in ("both",)  # short = fade fake UP-break at swing high
    allow_long = direction in ("both", "long")  # long = fade fake DOWN-break at swing low

    rows = []
    next_allowed = 0  # bar index at/after which new arms are allowed (no overlap)

    # -------- active "unbroken" pivot state, updated as we scan forward --------
    # active_high_level / active_high_idx: most recent confirmed-and-not-yet-
    # consumed pivot high (level to watch for a fake upside break)
    active_high_level = np.nan
    active_high_idx = -1
    high_break_j = -1       # bar index of the first break-bar beyond this level
    high_sweep_extreme = -np.inf

    active_low_level = np.nan
    active_low_idx = -1
    low_break_j = -1
    low_sweep_extreme = np.inf

    for i in range(n):
        a = atr[i]
        atr_ok = a > 0 and not np.isnan(a)

        # register newly-confirmed pivots at this bar (pivot at p=i-w confirmed
        # once we reach bar i == p+w; only look at pivots that are already
        # fully confirmed by info up to and including bar i -> no look-ahead)
        p = i - w
        if p >= w:  # pivot itself needs w bars on its left too
            if piv_high[p]:
                active_high_level = h[p]
                active_high_idx = p
                high_break_j = -1
                high_sweep_extreme = -np.inf
            if piv_low[p]:
                active_low_level = l[p]
                active_low_idx = p
                low_break_j = -1
                low_sweep_extreme = np.inf

        if i < next_allowed or not atr_ok:
            continue

        fired = False

        # ---------------- SHORT side: fake break above active_high_level -----
        if allow_short and active_high_idx >= 0 and i > active_high_idx:
            if h[i] > active_high_level + b_break * a:
                if high_break_j < 0:
                    high_break_j = i
                    high_sweep_extreme = h[i]
                else:
                    high_sweep_extreme = max(high_sweep_extreme, h[i])
            if high_break_j >= 0:
                bars_since = i - high_break_j
                if c[i] < active_high_level and bars_since <= N - 1:
                    # fake confirm -> SHORT
                    session_ok = (not session_filter) or (hour[i] in HIGH_LIQ_HOURS)
                    if session_ok:
                        sl_price = high_sweep_extreme + buf * a
                        sl_d = sl_price - c[i]
                        if sl_d > 0:
                            tp_price = c[i] - tp_r_mult * sl_d
                            rows.append((t[i], c[i], "SHORT", sl_price, tp_price, sl_d))
                            next_allowed = i + 1
                            fired = True
                    # level consumed either way (traded or session-filtered out)
                    active_high_idx = -1
                    active_high_level = np.nan
                    high_break_j = -1
                elif bars_since > N - 1:
                    # real breakout -> invalidate, stand down
                    active_high_idx = -1
                    active_high_level = np.nan
                    high_break_j = -1

        if fired:
            continue

        # ---------------- LONG side: fake break below active_low_level -------
        if allow_long and active_low_idx >= 0 and i > active_low_idx:
            if l[i] < active_low_level - b_break * a:
                if low_break_j < 0:
                    low_break_j = i
                    low_sweep_extreme = l[i]
                else:
                    low_sweep_extreme = min(low_sweep_extreme, l[i])
            if low_break_j >= 0:
                bars_since = i - low_break_j
                if c[i] > active_low_level and bars_since <= N - 1:
                    session_ok = (not session_filter) or (hour[i] in HIGH_LIQ_HOURS)
                    if session_ok:
                        sl_price = low_sweep_extreme - buf * a
                        sl_d = c[i] - sl_price
                        if sl_d > 0:
                            tp_price = c[i] + tp_r_mult * sl_d
                            rows.append((t[i], c[i], "LONG", sl_price, tp_price, sl_d))
                            next_allowed = i + 1
                    active_low_idx = -1
                    active_low_level = np.nan
                    low_break_j = -1
                elif bars_since > N - 1:
                    active_low_idx = -1
                    active_low_level = np.nan
                    low_break_j = -1

    cols = ["time_utc", "close", "action", "sl_price", "tp_price", "sl_distance"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)
