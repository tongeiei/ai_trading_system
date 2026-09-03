"""Market-structure detectors, lifted from falsified gold strategies (R11/R14/R15/R17)
and stripped of their entry/exit/SL/TP logic. See docs/XAU_ARCHITECTURE_AUDIT.md §8
NEW-3 for the rationale: these detectors were already debugged, only the *trading
edge* built on top of them was falsified.

All functions are causal (no lookahead): pivot at index p is only consumed once the
caller reaches i = p + w bars later, matching the original strategies' contract.
"""
import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
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


def compute_market_structure(
    m15: pd.DataFrame,
    atr_len: int = 14,
    w: int = 5,
    k_range: float = 2.0,
) -> pd.DataFrame:
    """Swing-fractal + BOS/CHoCH state machine, adapted from
    src/strategy/gold_r15_choch.py::compute_choch_events(). Adds an explicit
    bos_dir column (trend-continuation bars) alongside the original choch_dir.

    Returns one row per input bar: time_utc, atr, trend ("UP"/"DOWN"/"UNKNOWN"),
    bos_dir ("UP"/"DOWN"/None), choch_dir ("UP"/"DOWN"/None),
    last_swing_high, last_swing_low.
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
    bos_dir = np.array([None] * n, dtype=object)
    choch_dir = np.array([None] * n, dtype=object)
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

        fired_choch = None
        fired_bos = None
        a = atr[i]
        atr_ok = a > 0 and not np.isnan(a)
        range_ok = atr_ok and not np.isnan(last_high) and not np.isnan(last_low) and \
            (last_high - last_low) >= k_range * a

        if cur_trend == "UP" and not np.isnan(last_high) and not np.isnan(last_low):
            if c[i] > last_high:
                up_blocked = False
                fired_bos = "UP"
            elif c[i] < last_low:
                if not down_blocked and range_ok:
                    fired_choch = "DOWN"
                    down_blocked = True
                cur_trend = "DOWN"
        elif cur_trend == "DOWN" and not np.isnan(last_high) and not np.isnan(last_low):
            if c[i] < last_low:
                down_blocked = False
                fired_bos = "DOWN"
            elif c[i] > last_high:
                if not up_blocked and range_ok:
                    fired_choch = "UP"
                    up_blocked = True
                cur_trend = "UP"

        trend[i] = cur_trend
        bos_dir[i] = fired_bos
        choch_dir[i] = fired_choch
        last_high_out[i] = last_high
        last_low_out[i] = last_low

    out = df[["time_utc", "atr"]].copy()
    out["trend"] = trend
    out["bos_dir"] = bos_dir
    out["choch_dir"] = choch_dir
    out["last_swing_high"] = last_high_out
    out["last_swing_low"] = last_low_out
    return out


def compute_fvg_state(
    m15: pd.DataFrame,
    atr_len: int = 14,
    k_gap: float = 0.5,
    N: int = 10,
) -> pd.DataFrame:
    """Fair-value-gap per-bar state, adapted from the gap-detection core of
    src/strategy/gold_r17_fvg.py (the retest/trade logic there is dropped).

    A gap is "active" from the bar it forms until it's either retested (price
    trades back into the zone) or times out after N bars.

    Returns: time_utc, atr, bull_gap_active, bull_gap_low, bull_gap_high,
    bars_since_bull_gap, bear_gap_active, bear_gap_low, bear_gap_high,
    bars_since_bear_gap.
    """
    df = m15[["time_utc", "open", "high", "low", "close"]].copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)
    df["atr"] = _atr(df, atr_len)

    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    atr = df["atr"].to_numpy()
    n = len(df)

    bull_low = bull_high = np.nan
    bull_formed = -1
    bear_low = bear_high = np.nan
    bear_formed = -1

    bull_active_out = np.zeros(n, dtype=bool)
    bull_low_out = np.full(n, np.nan)
    bull_high_out = np.full(n, np.nan)
    bull_bars_since_out = np.full(n, np.nan)
    bear_active_out = np.zeros(n, dtype=bool)
    bear_low_out = np.full(n, np.nan)
    bear_high_out = np.full(n, np.nan)
    bear_bars_since_out = np.full(n, np.nan)

    for i in range(n):
        a = atr[i]
        atr_ok = a > 0 and not np.isnan(a)

        if i >= 2 and atr_ok:
            if l[i] > h[i - 2] and (l[i] - h[i - 2]) >= k_gap * a:
                bull_low, bull_high, bull_formed = h[i - 2], l[i], i
            if h[i] < l[i - 2] and (l[i - 2] - h[i]) >= k_gap * a:
                bear_low, bear_high, bear_formed = h[i], l[i - 2], i

        if bull_formed >= 0:
            bars_since = i - bull_formed
            if bars_since > N:
                bull_formed = -1
            else:
                bull_active_out[i] = True
                bull_low_out[i] = bull_low
                bull_high_out[i] = bull_high
                bull_bars_since_out[i] = bars_since
                if i > bull_formed and l[i] <= bull_high:
                    bull_formed = -1  # consumed by retest, inactive from next bar

        if bear_formed >= 0:
            bars_since = i - bear_formed
            if bars_since > N:
                bear_formed = -1
            else:
                bear_active_out[i] = True
                bear_low_out[i] = bear_low
                bear_high_out[i] = bear_high
                bear_bars_since_out[i] = bars_since
                if i > bear_formed and h[i] >= bear_low:
                    bear_formed = -1

    out = df[["time_utc", "atr"]].copy()
    out["bull_gap_active"] = bull_active_out
    out["bull_gap_low"] = bull_low_out
    out["bull_gap_high"] = bull_high_out
    out["bars_since_bull_gap"] = bull_bars_since_out
    out["bear_gap_active"] = bear_active_out
    out["bear_gap_low"] = bear_low_out
    out["bear_gap_high"] = bear_high_out
    out["bars_since_bear_gap"] = bear_bars_since_out
    return out


def compute_liquidity_sweep_state(
    m15: pd.DataFrame,
    atr_len: int = 14,
    w: int = 3,
    b_break: float = 0.5,
    N: int = 3,
) -> pd.DataFrame:
    """Pivot-sweep (liquidity sweep / fake breakout) per-bar state, adapted from
    the detection core of src/strategy/gold_r14_fake_zone.py (session filter and
    SL/TP/trade logic dropped).

    sweep_fired_dir is "UP" on the bar a fake break above a swing high is
    confirmed (fade -> short bias), "DOWN" for a fake break below a swing low
    (fade -> long bias), else None.

    Returns: time_utc, atr, active_high_level, high_break_bars_since,
    active_low_level, low_break_bars_since, sweep_fired_dir.
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

    active_high_level = np.nan
    active_high_idx = -1
    high_break_j = -1
    high_sweep_extreme = -np.inf

    active_low_level = np.nan
    active_low_idx = -1
    low_break_j = -1
    low_sweep_extreme = np.inf

    high_level_out = np.full(n, np.nan)
    high_bars_since_out = np.full(n, np.nan)
    low_level_out = np.full(n, np.nan)
    low_bars_since_out = np.full(n, np.nan)
    fired_out = np.array([None] * n, dtype=object)

    for i in range(n):
        a = atr[i]
        atr_ok = a > 0 and not np.isnan(a)

        p = i - w
        if p >= w:
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

        fired = None

        if atr_ok and active_high_idx >= 0 and i > active_high_idx:
            if h[i] > active_high_level + b_break * a:
                if high_break_j < 0:
                    high_break_j = i
                    high_sweep_extreme = h[i]
                else:
                    high_sweep_extreme = max(high_sweep_extreme, h[i])
            if high_break_j >= 0:
                bars_since = i - high_break_j
                if c[i] < active_high_level and bars_since <= N - 1:
                    fired = "UP"
                    active_high_idx = -1
                    active_high_level = np.nan
                    high_break_j = -1
                elif bars_since > N - 1:
                    active_high_idx = -1
                    active_high_level = np.nan
                    high_break_j = -1

        if atr_ok and fired is None and active_low_idx >= 0 and i > active_low_idx:
            if l[i] < active_low_level - b_break * a:
                if low_break_j < 0:
                    low_break_j = i
                    low_sweep_extreme = l[i]
                else:
                    low_sweep_extreme = min(low_sweep_extreme, l[i])
            if low_break_j >= 0:
                bars_since = i - low_break_j
                if c[i] > active_low_level and bars_since <= N - 1:
                    fired = "DOWN"
                    active_low_idx = -1
                    active_low_level = np.nan
                    low_break_j = -1
                elif bars_since > N - 1:
                    active_low_idx = -1
                    active_low_level = np.nan
                    low_break_j = -1

        high_level_out[i] = active_high_level
        high_bars_since_out[i] = (i - high_break_j) if high_break_j >= 0 else np.nan
        low_level_out[i] = active_low_level
        low_bars_since_out[i] = (i - low_break_j) if low_break_j >= 0 else np.nan
        fired_out[i] = fired

    out = df[["time_utc", "atr"]].copy()
    out["active_high_level"] = high_level_out
    out["high_break_bars_since"] = high_bars_since_out
    out["active_low_level"] = low_level_out
    out["low_break_bars_since"] = low_bars_since_out
    out["sweep_fired_dir"] = fired_out
    return out


def compute_wick_metrics(m15: pd.DataFrame, atr_len: int = 14) -> pd.DataFrame:
    """Single-bar wick/body geometry, vectorized from src/strategy/gold_r11_wick_fill.py
    (trigger thresholds and trade logic dropped, raw ATR-normalized ratios kept).

    Returns: time_utc, atr, lower_wick_atr, upper_wick_atr, body_atr.
    """
    df = m15[["time_utc", "open", "high", "low", "close"]].copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)
    df["atr"] = _atr(df, atr_len)

    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    body = (df["close"] - df["open"]).abs()
    atr_safe = df["atr"].replace(0, np.nan)

    out = df[["time_utc", "atr"]].copy()
    out["lower_wick_atr"] = lower_wick / atr_safe
    out["upper_wick_atr"] = upper_wick / atr_safe
    out["body_atr"] = body / atr_safe
    return out
