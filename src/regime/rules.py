"""Regime classification per PROJECT_PLAN.md §5.2 — 3 classes, rule-based.

NEWS_BLACKOUT is a no-op for crypto V1 (no economic-calendar blackout list yet,
that's §P6/V2 territory) — kept as a hook so the signature doesn't change later.
"""
import numpy as np
import pandas as pd

ADX_TREND_THRESHOLD = 22.0
TREND_STRENGTH_THRESHOLD = 0.5  # |ema50-ema200|/atr_h1


def classify_regime(
    features: pd.DataFrame,
    adx_threshold: float = ADX_TREND_THRESHOLD,
    trend_strength_threshold: float = TREND_STRENGTH_THRESHOLD,
) -> pd.Series:
    adx = features["f04_adx14_h1"]
    trend_strength = features["f03_h1_trend_atr"].abs()

    is_trend = (adx > adx_threshold) & (trend_strength > trend_strength_threshold)
    regime = np.where(is_trend, "TREND", "RANGE")
    return pd.Series(regime, index=features.index, name="regime")


def vol_multiplier(features: pd.DataFrame) -> pd.Series:
    """Continuous risk multiplier from ATR percentile — §5.2, avoids the
    cliff behavior a discrete HIGH_VOLATILITY class would create."""
    atr_pct = features["f08_atr_percentile"] * 100  # to 0-100 scale
    mult = (50.0 / atr_pct.clip(lower=1)).clip(lower=0.40, upper=1.0)
    return mult.rename("vol_multiplier")
