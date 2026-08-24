"""Look-ahead bias test per PROJECT_PLAN.md §20.1.

Core check: "run the pipeline on data with the last bar dropped — every
feature value for prior timestamps must be IDENTICAL." If dropping future
data changes a past feature value, that feature is peeking into the future.
"""
import numpy as np
import pandas as pd
import pytest

from src.features.engine import build_features


def _make_synthetic_ohlc(n: int, freq: str, start: str, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    times = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    price = 100 + np.cumsum(rng.normal(0, 0.5, size=n))
    high = price + rng.uniform(0, 1, size=n)
    low = price - rng.uniform(0, 1, size=n)
    open_ = price + rng.normal(0, 0.2, size=n)
    close = price
    volume = rng.uniform(10, 100, size=n)
    return pd.DataFrame({
        "time_utc": times, "open": open_, "high": high, "low": low,
        "close": close, "volume": volume,
    })


@pytest.fixture
def synthetic_data():
    # need enough H1 bars to warm up EMA200 and enough M15 bars to warm up
    # the 60-day ATR percentile window (5760 bars) plus some margin
    m15 = _make_synthetic_ohlc(6200, "15min", "2024-01-01")
    h1 = _make_synthetic_ohlc(1600, "1h", "2024-01-01")
    return m15, h1


def test_features_unchanged_when_future_bar_dropped(synthetic_data):
    m15, h1 = synthetic_data

    full = build_features(m15, h1)
    truncated = build_features(m15.iloc[:-1].copy(), h1)

    # compare every row that exists in both frames — must be bit-identical
    common_len = len(truncated)
    full_common = full.iloc[:common_len].reset_index(drop=True)
    truncated = truncated.reset_index(drop=True)

    feature_cols = [c for c in full.columns if c.startswith("f")]
    for col in feature_cols:
        pd.testing.assert_series_equal(
            full_common[col], truncated[col], check_names=False,
            obj=f"feature {col} changed when a future M15 bar was dropped — look-ahead bias",
        )


def test_features_unchanged_when_future_h1_bar_dropped(synthetic_data):
    m15, h1 = synthetic_data

    full = build_features(m15, h1)
    # drop the last H1 bar; only M15 timestamps that were as-of-joined to it should differ,
    # and since the join is backward-looking, no M15 bar should reference a *future* H1 bar anyway
    truncated = build_features(m15, h1.iloc[:-1].copy())

    feature_cols = [c for c in full.columns if c.startswith("f")]
    for col in feature_cols:
        pd.testing.assert_series_equal(
            full[col], truncated[col], check_names=False,
            obj=f"feature {col} changed when a future H1 bar was dropped — H1 look-ahead bias",
        )


def test_all_features_shifted_by_at_least_one_bar(synthetic_data):
    """Feature at row i must be computable from data available at bar i-1's
    close — i.e. row 0 (no prior bar) must be entirely NaN."""
    m15, h1 = synthetic_data
    features = build_features(m15, h1)
    feature_cols = [c for c in features.columns if c.startswith("f")]
    assert features.loc[0, feature_cols].isna().all(), (
        "row 0 has non-NaN features with no prior closed bar to compute from — "
        "shift(1) is missing somewhere"
    )
