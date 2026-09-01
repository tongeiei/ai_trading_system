"""R15 — CHoCH (Change of Character), XAU/USD spot.

Hypothesis (docs/research/R15_R17_SMC_PLAN.md, R15):
  Market structure alternates HH/HL (uptrend) or LH/LL (downtrend), tracked
  via confirmed swing (pivot) highs/lows. A CHoCH is the first bar to CLOSE
  back past the swing point that was propping up the *current* trend (not
  just a pullback, and distinct from a BOS which extends the same trend):
    - in an UP trend, close < last confirmed swing low  -> CHoCH down
    - in a DOWN trend, close > last confirmed swing high -> CHoCH up
  Mechanism: stop-losses of trend-followers sit just past that swing point
  (the standard placement); a close beyond it triggers a forced-liquidation
  cascade in the direction of the break. Distinct from R12 (ATR-range
  breakout, already falsified) in that the trigger level comes from
  confirmed swing structure, not a raw ATR-multiple range -- R12 is the
  mandatory baseline this must beat (see plan §7 kill criteria).

Trend state starts UNKNOWN and only initializes once a HH+HL (-> UP) or
LH+LL (-> DOWN) pair of confirmed swings is seen. A `range_ok` filter (swing
high-low distance >= k_range*ATR) screens out noise-sized structure. A
same-direction re-arm cooldown blocks firing a second CHoCH in the same
direction until a BOS (genuine continuation) confirms the trend it entered
-- this specifically targets choppy whipsaw (UP-CHoCH_down-UP-CHoCH_down...)
without ever confirming either leg.

Pivot confirmation follows the exact same no-look-ahead contract as
gold_r14_fake_zone.py: a pivot at index p is only known at bar p+w.
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
    n = len(high)
    is_piv = np.ones(n, dtype=bool)
    for k in range(1, w + 1):
        left = np.full(n, -np.inf)
        left[k:] = high[:-k]
        right = np.full(n, -np.inf)
        right[:-k] = high[k:]
        is_piv &= (high > left) & (high > right)
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


def compute_choch_events(
    m15: pd.DataFrame,
    atr_len: int = 14,
    w: int = 5,
    k_range: float = 2.0,
) -> pd.DataFrame:
    """Runs the structure state machine and returns one row per bar with the
    live state (trend, last confirmed swing high/low, whether a CHoCH fired
    this bar and in which direction). Exposed separately from
    generate_r15_signals so R16 (order block) can reuse the exact same
    structure/CHoCH definition instead of re-deriving it -- keeps the two
    hypotheses from silently diverging on what "CHoCH" means.

    No look-ahead: last_high/last_low used at bar i are pivots confirmed by
    bar i (i.e. from bar p = i-w or earlier); CHoCH itself fires on close[i].
    """
    df = m15[["time_utc", "open", "high", "low", "close"]].copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)
    df["atr"] = _atr(df, atr_len)

    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    atr = df["atr"].to_numpy()
    n = len(df)

    piv_high = _pivot_highs(h, w)
    piv_low = _pivot_lows(l, w)

    trend = np.empty(n, dtype=object)
    choch_dir = np.array([None] * n, dtype=object)  # "UP" | "DOWN" | None
    last_high_out = np.full(n, np.nan)
    last_low_out = np.full(n, np.nan)

    cur_trend = "UNKNOWN"
    last_high = last_low = np.nan
    prev_high = prev_low = np.nan
    down_blocked = False
    up_blocked = False

    for i in range(n):
        p = i - w
        if p >= w:
            if piv_high[p]:
                prev_high = last_high
                last_high = h[p]
            if piv_low[p]:
                prev_low = last_low
                last_low = l[p]
            if cur_trend == "UNKNOWN" and not any(np.isnan(x) for x in (last_high, last_low, prev_high, prev_low)):
                if last_high > prev_high and last_low > prev_low:
                    cur_trend = "UP"
                elif last_high < prev_high and last_low < prev_low:
                    cur_trend = "DOWN"

        fired_dir = None
        a = atr[i]
        atr_ok = a > 0 and not np.isnan(a)
        range_ok = atr_ok and not np.isnan(last_high) and not np.isnan(last_low) and \
            (last_high - last_low) >= k_range * a

        if cur_trend == "UP" and not np.isnan(last_high) and not np.isnan(last_low):
            if c[i] > last_high:
                up_blocked = False  # BOS: UP trend genuinely continues
            elif c[i] < last_low:
                if not down_blocked and range_ok:
                    fired_dir = "DOWN"
                    down_blocked = True
                cur_trend = "DOWN"
        elif cur_trend == "DOWN" and not np.isnan(last_high) and not np.isnan(last_low):
            if c[i] < last_low:
                down_blocked = False  # BOS: DOWN trend genuinely continues
            elif c[i] > last_high:
                if not up_blocked and range_ok:
                    fired_dir = "UP"
                    up_blocked = True
                cur_trend = "UP"

        trend[i] = cur_trend
        choch_dir[i] = fired_dir
        last_high_out[i] = last_high
        last_low_out[i] = last_low

    out = df[["time_utc", "open", "high", "low", "close", "atr"]].copy()
    out["trend"] = trend
    out["choch_dir"] = choch_dir
    out["last_swing_high"] = last_high_out
    out["last_swing_low"] = last_low_out
    return out


def generate_r15_signals(
    m15: pd.DataFrame,
    atr_len: int = 14,
    w: int = 5,
    k_range: float = 2.0,
    buf: float = 0.1,
    tp_r_mult: float = 1.5,
    direction: str = "both",       # "both" | "long"
    session_filter: bool = True,
) -> pd.DataFrame:
    events = compute_choch_events(m15, atr_len=atr_len, w=w, k_range=k_range)
    events["hour"] = events["time_utc"].dt.hour

    allow_long = direction in ("both", "long")
    allow_short = direction in ("both",)

    rows = []
    n = len(events)
    next_allowed = 0
    t = events["time_utc"].to_numpy()
    c = events["close"].to_numpy()
    a = events["atr"].to_numpy()
    hi = events["last_swing_high"].to_numpy()
    lo = events["last_swing_low"].to_numpy()
    cdir = events["choch_dir"].to_numpy()
    hour = events["hour"].to_numpy()

    for i in range(n):
        if i < next_allowed or cdir[i] is None:
            continue
        session_ok = (not session_filter) or (hour[i] in HIGH_LIQ_HOURS)
        if not session_ok:
            continue
        if cdir[i] == "UP" and allow_long:
            sl_price = lo[i] - buf * a[i]
            sl_d = c[i] - sl_price
            if sl_d > 0:
                tp_price = c[i] + tp_r_mult * sl_d
                rows.append((t[i], c[i], "LONG", sl_price, tp_price, sl_d))
                next_allowed = i + 1
        elif cdir[i] == "DOWN" and allow_short:
            sl_price = hi[i] + buf * a[i]
            sl_d = sl_price - c[i]
            if sl_d > 0:
                tp_price = c[i] - tp_r_mult * sl_d
                rows.append((t[i], c[i], "SHORT", sl_price, tp_price, sl_d))
                next_allowed = i + 1

    cols = ["time_utc", "close", "action", "sl_price", "tp_price", "sl_distance"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)
