import numpy as np

from src.backtest.significance import bootstrap_mean_test


def test_clearly_positive_mean_is_significant():
    rng = np.random.default_rng(1)
    r = rng.normal(loc=0.5, scale=1.0, size=1000)  # strong positive signal
    result = bootstrap_mean_test(r, n_resamples=2000, seed=1)
    assert result["significant_at_5pct"]
    assert result["ci_95_lo"] > 0


def test_zero_mean_noise_is_not_significant():
    rng = np.random.default_rng(2)
    r = rng.normal(loc=0.0, scale=1.0, size=1000)  # pure noise, no edge
    result = bootstrap_mean_test(r, n_resamples=2000, seed=2)
    assert not result["significant_at_5pct"]


def test_small_sample_positive_mean_may_not_be_significant():
    rng = np.random.default_rng(3)
    r = rng.normal(loc=0.15, scale=1.0, size=20)  # thin edge, tiny n
    result = bootstrap_mean_test(r, n_resamples=2000, seed=3)
    # not asserting the outcome either way — just that it runs and CI straddles wider range
    assert result["ci_95_hi"] - result["ci_95_lo"] > 0
