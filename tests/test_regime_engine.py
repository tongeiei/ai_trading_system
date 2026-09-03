"""Unit tests for src/regime/engine.py -- the 5-class regime engine (NEW module,
separate from the locked src/regime/rules.py::classify_regime -- see
docs/XAU_ARCHITECTURE_AUDIT.md §17)."""
import json

import numpy as np
import pandas as pd

from src.data.db import init_db, regime_states
from src.live.logging_store import log_regime_states
from src.regime.engine import REGIME_CLASSES, classify_regime_v2


def _features(n=10, adx=15.0, trend_atr=0.1, atr_pct=0.5, vol_exp=1.0):
    times = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({
        "time_utc": times,
        "f03_h1_trend_atr": [trend_atr] * n,
        "f04_adx14_h1": [adx] * n,
        "f08_atr_percentile": [atr_pct] * n,
        "f09_vol_expansion_ratio": [vol_exp] * n,
    })


def test_trend_fires_on_high_adx_and_trend_strength():
    out = classify_regime_v2(_features(adx=40.0, trend_atr=1.0, atr_pct=0.5, vol_exp=1.0))
    assert (out["regime"] == "TREND").all()
    assert (out["regime_confidence"] > 0).all()


def test_range_fires_on_low_adx():
    out = classify_regime_v2(_features(adx=5.0, trend_atr=0.05, atr_pct=0.5, vol_exp=1.0))
    assert (out["regime"] == "RANGE").all()


def test_volatility_expansion_takes_precedence_over_trend():
    out = classify_regime_v2(_features(adx=40.0, trend_atr=1.0, atr_pct=0.5, vol_exp=3.0))
    assert (out["regime"] == "VOLATILITY_EXPANSION").all()


def test_high_volatility_fires_on_high_atr_percentile():
    out = classify_regime_v2(_features(adx=5.0, trend_atr=0.05, atr_pct=0.95, vol_exp=1.0))
    assert (out["regime"] == "HIGH_VOLATILITY").all()


def test_unknown_fires_on_nan_features():
    f = _features()
    f.loc[0, "f04_adx14_h1"] = np.nan
    out = classify_regime_v2(f)
    assert out.loc[0, "regime"] == "UNKNOWN"
    assert out.loc[0, "regime_confidence"] == 0.0
    assert out.loc[1, "regime"] != "UNKNOWN"


def test_confidence_always_in_unit_range():
    f = _features(adx=100.0, trend_atr=5.0, atr_pct=1.0, vol_exp=10.0)
    out = classify_regime_v2(f)
    assert (out["regime_confidence"] >= 0).all()
    assert (out["regime_confidence"] <= 1).all()


def test_regime_features_is_valid_json():
    out = classify_regime_v2(_features())
    parsed = json.loads(out.loc[0, "regime_features"])
    assert set(parsed.keys()) == {
        "f03_h1_trend_atr", "f04_adx14_h1", "f08_atr_percentile", "f09_vol_expansion_ratio",
    }


def test_only_known_classes_appear():
    f = _features(n=1)
    f.loc[0, "f04_adx14_h1"] = np.nan
    mixed = pd.concat([
        _features(n=3, adx=40.0, trend_atr=1.0, vol_exp=1.0),
        _features(n=3, adx=5.0, trend_atr=0.05, vol_exp=1.0),
        _features(n=3, adx=5.0, atr_pct=0.95, vol_exp=1.0),
        _features(n=3, vol_exp=3.0),
        f,
    ], ignore_index=True)
    out = classify_regime_v2(mixed)
    assert set(out["regime"].unique()) <= set(REGIME_CLASSES)


def test_log_regime_states_round_trip(tmp_path):
    engine = init_db(str(tmp_path / "test.db"))
    df = classify_regime_v2(_features(n=5, adx=40.0, trend_atr=1.0))
    log_regime_states(engine, "XAUUSD", "M15", df)

    from sqlalchemy import select
    with engine.connect() as conn:
        rows = conn.execute(select(regime_states)).fetchall()
    assert len(rows) == 5
    assert rows[0].symbol == "XAUUSD"
    assert rows[0].timeframe == "M15"
    assert rows[0].regime == "TREND"
    assert json.loads(rows[0].regime_features)["f04_adx14_h1"] == 40.0
