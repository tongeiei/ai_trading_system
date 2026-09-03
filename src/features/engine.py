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

from src.features.structure import (
    compute_fvg_state,
    compute_liquidity_sweep_state,
    compute_market_structure,
    compute_wick_metrics,
)

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


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _session_vwap(df: pd.DataFrame) -> pd.Series:
    """Typical-price VWAP, reset every UTC calendar day (no lookahead: cumulative
    sums only use bars up to and including the current one)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    day = df["time_utc"].dt.floor("D")
    pv = (typical * df["volume"]).groupby(day).cumsum()
    vol = df["volume"].groupby(day).cumsum()
    return pv / vol.replace(0, np.nan)


def build_features(m15: pd.DataFrame, h1: pd.DataFrame, h4: pd.DataFrame | None = None) -> pd.DataFrame:
    """m15/h1/h4: columns [time_utc, open, high, low, close, volume], time-sorted.
    Returns a feature frame aligned to m15 bar-close times, with h1/h4 context
    merged via as-of (backward) join so no future H1/H4 bar ever leaks in.

    h4 is optional (default None) so existing 2-arg callers (src/live/signal_service.py,
    src/backtest/gold_harness.py) keep working unmodified -- f34/f35 are NaN when
    h4 is not supplied.
    """
    m15 = m15.sort_values("time_utc").reset_index(drop=True).copy()
    h1 = h1.sort_values("time_utc").reset_index(drop=True).copy()

    # --- M15-native indicators ---
    m15["ema20"] = _ema(m15["close"], 20)
    m15["ema50"] = _ema(m15["close"], 50)
    m15["ema200"] = _ema(m15["close"], 200)
    m15["atr14"] = _atr(m15, 14)
    m15["adx14"] = _adx(m15, 14)
    m15["rsi14"] = _rsi(m15["close"], 14)
    m15["vwap"] = _session_vwap(m15) if "volume" in m15.columns else np.nan

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

    f["f13_adx14_m15"] = m15["adx14"]
    f["f14_dist_ema200_atr"] = (m15["close"] - m15["ema200"]) / m15["atr14"]
    ema200_slope = m15["ema200"] - m15["ema200"].shift(12)  # ~3h of M15 bars
    f["f15_ema200_slope_atr"] = ema200_slope / m15["atr14"]
    f["f16_rsi14"] = m15["rsi14"]
    f["f17_dist_vwap_atr"] = (m15["close"] - m15["vwap"]) / m15["atr14"]
    f["f18_day_of_week"] = m15["time_utc"].dt.dayofweek

    # --- market-structure features (src/features/structure.py, lifted from
    # falsified gold strategies R11/R14/R15/R17 -- see docs/XAU_ARCHITECTURE_AUDIT.md
    # §8 NEW-3). Symbol-agnostic: computed for crypto too, harmless (additive columns,
    # no existing consumer reads by position/count -- see P3 plan).
    struct = compute_market_structure(m15)
    f["f19_dist_swing_high_atr"] = (struct["last_swing_high"] - m15["close"]) / struct["atr"]
    f["f20_dist_swing_low_atr"] = (m15["close"] - struct["last_swing_low"]) / struct["atr"]
    trend_code = struct["trend"].map({"UP": 1, "DOWN": -1, "UNKNOWN": 0})
    f["f21_trend_state"] = trend_code
    f["f22_bos_fired"] = struct["bos_dir"].map({"UP": 1, "DOWN": -1}).fillna(0)
    f["f23_choch_fired"] = struct["choch_dir"].map({"UP": 1, "DOWN": -1}).fillna(0)

    fvg = compute_fvg_state(m15)
    f["f24_bull_fvg_active"] = fvg["bull_gap_active"].astype(float)
    f["f25_dist_bull_fvg_atr"] = (m15["close"] - fvg["bull_gap_high"]) / fvg["atr"]
    f["f26_bars_since_bull_fvg"] = fvg["bars_since_bull_gap"]
    f["f27_bear_fvg_active"] = fvg["bear_gap_active"].astype(float)
    f["f28_dist_bear_fvg_atr"] = (fvg["bear_gap_low"] - m15["close"]) / fvg["atr"]
    f["f29_bars_since_bear_fvg"] = fvg["bars_since_bear_gap"]

    sweep = compute_liquidity_sweep_state(m15)
    f["f30_liquidity_sweep_dir"] = sweep["sweep_fired_dir"].map({"UP": 1, "DOWN": -1}).fillna(0)

    wick = compute_wick_metrics(m15)
    f["f31_wick_lower_atr"] = wick["lower_wick_atr"]
    f["f32_wick_upper_atr"] = wick["upper_wick_atr"]
    f["f33_body_atr"] = wick["body_atr"]

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
    # No genuine historical per-bar spread series exists for backtest (crypto or gold)
    # as of P3 -- this stays NaN for all backtests; only a future live wiring
    # (src/data/mt5_feed.py currently drops MT5's tick-level spread field) could fill it.
    f["f12_spread_ratio"] = np.nan

    # --- H4 context, as-of backward join (optional -- NaN when h4 not supplied) ---
    if h4 is not None:
        h4c = h4.sort_values("time_utc").reset_index(drop=True).copy()
        h4c["ema50_h4"] = _ema(h4c["close"], 50)
        h4c["ema200_h4"] = _ema(h4c["close"], 200)
        h4c["atr14_h4"] = _atr(h4c, 14)
        h4c["adx14_h4"] = _adx(h4c, 14)
        joined_h4 = pd.merge_asof(
            f[["time_utc"]], h4c[["time_utc", "ema50_h4", "ema200_h4", "atr14_h4", "adx14_h4"]],
            on="time_utc", direction="backward",
        )
        f["f34_h4_trend_atr"] = (joined_h4["ema50_h4"] - joined_h4["ema200_h4"]) / joined_h4["atr14_h4"]
        f["f35_adx14_h4"] = joined_h4["adx14_h4"]
    else:
        f["f34_h4_trend_atr"] = np.nan
        f["f35_adx14_h4"] = np.nan

    feature_cols = [c for c in f.columns if c.startswith("f")]
    # rule #1: every feature must reflect only the bar BEFORE the decision point
    f[feature_cols] = f[feature_cols].shift(1)

    return f
