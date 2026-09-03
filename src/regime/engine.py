"""5-class regime engine per TASK_NEW_WORLD.md §7 (TREND/RANGE/VOLATILITY_EXPANSION/
HIGH_VOLATILITY/UNKNOWN), with persisted confidence + underlying features.

This is a NEW, separate module from src/regime/rules.py::classify_regime -- that
function is locked (used by the live ETH/XRP pipeline via src/live/signal_service.py,
and by ~25 research scripts that reproduce numbers already recorded in
docs/FINDINGS.md). Do not merge this into rules.py or change its output classes;
see docs/XAU_ARCHITECTURE_AUDIT.md §17 for the rationale.

Classification rules and the confidence formula are a new design choice made for
this phase (not specified anywhere in the source docs beyond the 5 class names) --
not yet backtested/validated, same status as the rest of the not-yet-tested target
architecture.
"""
import json

import numpy as np
import pandas as pd

REGIME_CLASSES = ["TREND", "RANGE", "VOLATILITY_EXPANSION", "HIGH_VOLATILITY", "UNKNOWN"]

REQUIRED_FEATURE_COLS = [
    "f03_h1_trend_atr", "f04_adx14_h1", "f08_atr_percentile", "f09_vol_expansion_ratio",
]


def classify_regime_v2(
    features: pd.DataFrame,
    adx_threshold: float = 22.0,
    trend_strength_threshold: float = 0.5,
    vol_expansion_threshold: float = 1.5,
    high_vol_percentile: float = 0.90,
) -> pd.DataFrame:
    """Precedence per bar (classes are not mutually exclusive by nature, so this
    order is a deliberate design choice, not a derived fact):
      1. UNKNOWN               -- any required feature is NaN (warm-up period)
      2. VOLATILITY_EXPANSION  -- f09_vol_expansion_ratio > vol_expansion_threshold
                                   (checked before TREND: a sudden vol expansion is
                                   the most actionable/rare signal and shouldn't be
                                   masked by a coincident high-ADX reading)
      3. HIGH_VOLATILITY       -- f08_atr_percentile > high_vol_percentile
      4. TREND                 -- same condition as rules.py::classify_regime
      5. RANGE                 -- else

    Returns a DataFrame: time_utc, regime, regime_confidence, regime_features (JSON
    string of the underlying feature values used for the decision).
    """
    adx = features["f04_adx14_h1"]
    trend_strength = features["f03_h1_trend_atr"].abs()
    atr_pct = features["f08_atr_percentile"]
    vol_expansion = features["f09_vol_expansion_ratio"]

    missing = features[REQUIRED_FEATURE_COLS].isna().any(axis=1)
    is_expansion = ~missing & (vol_expansion > vol_expansion_threshold)
    is_high_vol = ~missing & ~is_expansion & (atr_pct > high_vol_percentile)
    is_trend = (
        ~missing & ~is_expansion & ~is_high_vol
        & (adx > adx_threshold) & (trend_strength > trend_strength_threshold)
    )

    regime = np.select(
        [missing, is_expansion, is_high_vol, is_trend],
        ["UNKNOWN", "VOLATILITY_EXPANSION", "HIGH_VOLATILITY", "TREND"],
        default="RANGE",
    )

    confidence = pd.Series(0.0, index=features.index)
    confidence[is_expansion] = ((vol_expansion - vol_expansion_threshold) / vol_expansion_threshold).clip(0, 1)[is_expansion]
    confidence[is_high_vol] = ((atr_pct - high_vol_percentile) / (1 - high_vol_percentile)).clip(0, 1)[is_high_vol]
    confidence[is_trend] = ((adx - adx_threshold) / adx_threshold).clip(0, 1)[is_trend]
    range_mask = (regime == "RANGE")
    confidence[range_mask] = (1 - (adx / adx_threshold).clip(0, 1))[range_mask]

    def _features_json(row):
        return json.dumps({
            "f03_h1_trend_atr": None if pd.isna(row["f03_h1_trend_atr"]) else float(row["f03_h1_trend_atr"]),
            "f04_adx14_h1": None if pd.isna(row["f04_adx14_h1"]) else float(row["f04_adx14_h1"]),
            "f08_atr_percentile": None if pd.isna(row["f08_atr_percentile"]) else float(row["f08_atr_percentile"]),
            "f09_vol_expansion_ratio": None if pd.isna(row["f09_vol_expansion_ratio"]) else float(row["f09_vol_expansion_ratio"]),
        })

    out = pd.DataFrame({
        "time_utc": features["time_utc"],
        "regime": regime,
        "regime_confidence": confidence,
    })
    out["regime_features"] = features[REQUIRED_FEATURE_COLS + ["time_utc"]].apply(_features_json, axis=1)
    return out
