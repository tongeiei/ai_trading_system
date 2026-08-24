"""12-feature set per PROJECT_PLAN.md §4.2.

Hard rules (§4.2):
  1. every feature uses only closed bars -> always shift(1) after computing
  2. rolling stats (percentile, median) look backward only, never whole-dataset
  3. new features only earn a place after permutation-importance on OOS data

session windows are UTC-based; adjust SESSION_HOURS_UTC if your definition
of London/NY/Asia differs.
"""
import numpy as np
import pandas as pd

SESSION_HOURS_UTC = {
    "ASIA": (0, 8),
    "LONDON": (8, 13),
    "OVERLAP": (13, 16),
    "NY": (16, 21),
    "OFF": (21, 24),
}


def _session_for_hour(hour: int) -> str:
    for name, (start, end) in SESSION_HOURS_UTC.items():
        if start <= hour < end:
            return name
    return "OFF"


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr = _atr(df, period)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def build_features(m15: pd.DataFrame, h1: pd.DataFrame) -> pd.DataFrame:
    """m15/h1: columns [time_utc, open, high, low, close, volume], time-sorted.
    Returns a feature frame aligned to m15 bar-close times, with h1 context
    merged via as-of (backward) join so no future H1 bar ever leaks in.
    """
    m15 = m15.sort_values("time_utc").reset_index(drop=True).copy()
    h1 = h1.sort_values("time_utc").reset_index(drop=True).copy()

    # --- M15-native indicators ---
    m15["ema20"] = _ema(m15["close"], 20)
    m15["ema50"] = _ema(m15["close"], 50)
    m15["atr14"] = _atr(m15, 14)

    f = pd.DataFrame(index=m15.index)
    f["time_utc"] = m15["time_utc"]

    f["f01_dist_ema20_atr"] = (m15["close"] - m15["ema20"]) / m15["atr14"]
    f["f02_dist_ema50_atr"] = (m15["close"] - m15["ema50"]) / m15["atr14"]
    f["f05_logret_4"] = np.log(m15["close"] / m15["close"].shift(4))
    f["f06_logret_12"] = np.log(m15["close"] / m15["close"].shift(12))
    f["f07_atr_norm"] = m15["atr14"] / m15["close"]

    atr_pct = m15["atr14"].rolling(window=5760, min_periods=200).rank(pct=True)  # ~60 days of M15 bars
    f["f08_atr_percentile"] = atr_pct

    atr_24_ago = m15["atr14"].shift(24)
    f["f09_vol_expansion_ratio"] = m15["atr14"] / atr_24_ago

    body = (m15["close"] - m15["open"]).abs()
    rng = (m15["high"] - m15["low"]).replace(0, np.nan)
    f["f10_candle_body_ratio"] = body / rng

    f["session"] = m15["time_utc"].dt.hour.map(_session_for_hour)

    # --- H1 context, as-of backward join (only sees H1 bars fully closed before this M15 bar) ---
    h1c = h1.copy()
    h1c["ema50_h1"] = _ema(h1c["close"], 50)
    h1c["ema200_h1"] = _ema(h1c["close"], 200)
    h1c["atr14_h1"] = _atr(h1c, 14)
    h1c["adx14_h1"] = _adx(h1c, 14)

    joined = pd.merge_asof(
        f[["time_utc"]], h1c[["time_utc", "ema50_h1", "ema200_h1", "atr14_h1", "adx14_h1"]],
        on="time_utc", direction="backward",
    )
    f["f03_h1_trend_atr"] = (joined["ema50_h1"] - joined["ema200_h1"]) / joined["atr14_h1"]
    f["f04_adx14_h1"] = joined["adx14_h1"]

    # spread feature (f12) needs live spread data — placeholder until execution
    # layer provides it; NaN here is intentional, filled at signal time in live/backtest.
    f["f12_spread_ratio"] = np.nan

    feature_cols = [c for c in f.columns if c.startswith("f")]
    # rule #1: every feature must reflect only the bar BEFORE the decision point
    f[feature_cols] = f[feature_cols].shift(1)

    return f
