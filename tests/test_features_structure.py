"""Unit tests for src/features/structure.py detectors (lifted from falsified gold
strategies R11/R14/R15/R17, entry/exit logic stripped -- see docs/XAU_ARCHITECTURE_AUDIT.md
§8 NEW-3)."""
import numpy as np
import pandas as pd
import pytest

from src.features.structure import (
    _pivot_highs,
    _pivot_lows,
    compute_fvg_state,
    compute_liquidity_sweep_state,
    compute_market_structure,
    compute_wick_metrics,
)


def _bars(n, base=2000.0, step=1.0):
    """Flat-ish OHLC bars, one per M15, for scaffolding synthetic patterns."""
    times = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    close = np.full(n, base)
    df = pd.DataFrame({
        "time_utc": times,
        "open": close.copy(),
        "high": close + step,
        "low": close - step,
        "close": close.copy(),
    })
    return df


def test_pivot_highs_detects_local_max():
    high = np.array([1, 2, 3, 5, 3, 2, 1, 2, 3, 2, 1], dtype=float)
    piv = _pivot_highs(high, w=2)
    assert piv[3]  # value 5 is a strict local max within +-2 bars
    assert piv[8]  # value 3 at index 8 is also a strict local max within +-2 bars


def test_pivot_lows_detects_local_min():
    low = np.array([5, 4, 3, 1, 3, 4, 5, 4, 3, 4, 5], dtype=float)
    piv = _pivot_lows(low, w=2)
    assert piv[3]


def test_pivot_edges_never_flagged():
    high = np.array([10, 9, 8, 7, 6, 7, 8, 9, 10], dtype=float)
    piv = _pivot_highs(high, w=3)
    assert not piv[:3].any()
    assert not piv[-3:].any()


def test_market_structure_choch_fires_on_break():
    n = 60
    df = _bars(n)
    close = df["close"].to_numpy().copy()
    high = df["high"].to_numpy().copy()
    low = df["low"].to_numpy().copy()
    # zigzag with rising swing highs/lows (clear uptrend structure), each leg 5 bars
    swing_lows = [2000, 2010, 2020, 2030, 2040]
    swing_highs = [2015, 2025, 2035, 2045, 2055]
    for leg in range(5):
        base_i = leg * 10
        lo, hi = swing_lows[leg], swing_highs[leg]
        for j in range(5):  # down leg touching swing low at mid-point
            i = base_i + j
            close[i] = hi - (hi - lo) * abs(j - 2) / 2
        for j in range(5):  # up leg touching swing high at mid-point
            i = base_i + 5 + j
            close[i] = lo + (hi - lo) * (1 - abs(j - 2) / 2)
    high[:] = close + 1.0
    low[:] = close - 1.0
    # then crash well below the most recent swing low to force a DOWN CHoCH
    close[-5:] = 1900.0
    high[-5:] = 1901.0
    low[-5:] = 1899.0
    df["open"], df["close"], df["high"], df["low"] = close, close, high, low

    out = compute_market_structure(df, atr_len=14, w=2, k_range=0.0)
    assert set(out["trend"].unique()) <= {"UNKNOWN", "UP", "DOWN"}
    assert out["choch_dir"].notna().any() or out["trend"].iloc[-1] == "DOWN"


def test_market_structure_no_lookahead():
    df = _bars(80)
    rng = np.random.default_rng(0)
    df["close"] = 2000 + np.cumsum(rng.normal(0, 1, size=80))
    df["open"] = df["close"]
    df["high"] = df["close"] + rng.uniform(0.5, 2, size=80)
    df["low"] = df["close"] - rng.uniform(0.5, 2, size=80)

    full = compute_market_structure(df, atr_len=14, w=4, k_range=0.0)
    truncated = compute_market_structure(df.iloc[:-5], atr_len=14, w=4, k_range=0.0)
    overlap = len(truncated)
    pd.testing.assert_series_equal(
        full["trend"].iloc[:overlap].reset_index(drop=True),
        truncated["trend"].reset_index(drop=True),
        check_names=False,
    )


def test_fvg_detects_bullish_gap():
    n = 20
    df = _bars(n)
    high = df["high"].to_numpy().copy()
    low = df["low"].to_numpy().copy()
    close = df["close"].to_numpy().copy()
    open_ = df["open"].to_numpy().copy()
    # bar 9: high[7] far below low[9] -> bullish gap forms at i=9
    high[7] = 1990.0
    low[9] = 2010.0
    close[9] = 2011.0
    open_[9] = 2009.0
    df["high"], df["low"], df["close"], df["open"] = high, low, close, open_

    out = compute_fvg_state(df, atr_len=5, k_gap=0.1, N=10)
    assert out["bull_gap_active"].iloc[9]
    assert out["bull_gap_low"].iloc[9] == pytest.approx(1990.0)
    assert out["bull_gap_high"].iloc[9] == pytest.approx(2010.0)


def test_fvg_gap_times_out():
    n = 30
    df = _bars(n)
    high = df["high"].to_numpy().copy()
    low = df["low"].to_numpy().copy()
    high[7] = 1990.0
    low[9] = 2010.0
    df["high"], df["low"] = high, low
    out = compute_fvg_state(df, atr_len=5, k_gap=0.1, N=3)
    assert not out["bull_gap_active"].iloc[20]


def test_liquidity_sweep_fires_on_fake_break_above():
    n = 40
    df = _bars(n)
    high = df["high"].to_numpy().copy()
    low = df["low"].to_numpy().copy()
    close = df["close"].to_numpy().copy()
    open_ = df["open"].to_numpy().copy()

    piv_idx = 15
    high[piv_idx] = 2010.0
    # break above then close back below -> fake break confirmed
    break_idx = piv_idx + 5
    high[break_idx] = 2020.0
    close[break_idx] = 2015.0
    confirm_idx = break_idx + 1
    close[confirm_idx] = 2005.0
    open_[confirm_idx] = 2015.0
    high[confirm_idx] = 2016.0
    low[confirm_idx] = 2004.0

    df["high"], df["low"], df["close"], df["open"] = high, low, close, open_
    out = compute_liquidity_sweep_state(df, atr_len=5, w=3, b_break=0.1, N=5)
    assert (out["sweep_fired_dir"] == "UP").any()


def test_wick_metrics_basic_geometry():
    df = pd.DataFrame({
        "time_utc": pd.date_range("2024-01-01", periods=20, freq="15min", tz="UTC"),
        "open": [2000.0] * 20,
        "close": [2001.0] * 20,
        "high": [2001.0] * 19 + [2010.0],
        "low": [1999.0] * 19 + [1995.0],
    })
    out = compute_wick_metrics(df, atr_len=5)
    assert out["lower_wick_atr"].iloc[-1] > 0
    assert out["upper_wick_atr"].iloc[-1] > 0
    assert out["body_atr"].iloc[-1] >= 0
