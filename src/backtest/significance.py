"""Bootstrap significance testing — PROJECT_PLAN.md §14.4/§P5.

Tests whether an observed mean R is distinguishable from zero (or from
another strategy's mean, for paired comparisons) given sampling noise.
"""
import numpy as np


def bootstrap_mean_test(r_values: np.ndarray, n_resamples: int = 10_000, seed: int = 0) -> dict:
    """One-sample bootstrap: is mean(r_values) significantly > 0?
    Returns observed mean, bootstrap 95% CI, and a two-sided p-value
    (fraction of resamples with mean <= 0, doubled).
    """
    rng = np.random.default_rng(seed)
    r_values = np.asarray(r_values)
    n = len(r_values)
    observed_mean = r_values.mean()

    boot_means = np.empty(n_resamples)
    for i in range(n_resamples):
        sample = rng.choice(r_values, size=n, replace=True)
        boot_means[i] = sample.mean()

    ci_lo, ci_hi = np.percentile(boot_means, [2.5, 97.5])
    # p-value for H0: true mean <= 0, via how often bootstrap mean crosses 0
    p_value = 2 * min((boot_means <= 0).mean(), (boot_means > 0).mean())

    return {
        "n": n,
        "observed_mean": observed_mean,
        "ci_95_lo": ci_lo,
        "ci_95_hi": ci_hi,
        "p_value": p_value,
        "significant_at_5pct": p_value < 0.05 and ci_lo > 0,
    }
