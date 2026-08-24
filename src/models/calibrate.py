"""Probability calibration + evaluation per PROJECT_PLAN.md §7.

Isotonic must be fit on a fold DISJOINT from train (§7.1) — the caller is
responsible for passing calibration-fold data, never train-fold data here.
"""
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, roc_auc_score


def fit_isotonic(p_raw_cal: np.ndarray, y_cal: np.ndarray) -> IsotonicRegression:
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(p_raw_cal, y_cal)
    return calibrator


def expected_calibration_error(p_cal: np.ndarray, y: np.ndarray, n_bins: int = 10) -> tuple[float, pd.DataFrame]:
    """Returns (ECE, per-bin breakdown). §7.2/§7.3 — bins with n<30 get flagged."""
    bins = np.linspace(0, 1, n_bins + 1)
    bin_idx = np.digitize(p_cal, bins[1:-1])
    rows = []
    ece = 0.0
    n_total = len(p_cal)
    for b in range(n_bins):
        mask = bin_idx == b
        n = mask.sum()
        if n == 0:
            continue
        mean_pred = p_cal[mask].mean()
        observed_rate = y[mask].mean()
        # Wilson 95% CI for observed rate
        ci_lo, ci_hi = _wilson_ci(y[mask].sum(), n)
        rows.append({
            "bin_lo": bins[b], "bin_hi": bins[b + 1], "n": int(n),
            "mean_pred": mean_pred, "observed_rate": observed_rate,
            "ci_lo": ci_lo, "ci_hi": ci_hi,
            "trustworthy": n >= 30 and ci_lo <= mean_pred <= ci_hi,
        })
        ece += (n / n_total) * abs(mean_pred - observed_rate)
    return ece, pd.DataFrame(rows)


def _wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = (z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def evaluate_calibration(p_cal: np.ndarray, y: np.ndarray) -> dict:
    auc = roc_auc_score(y, p_cal)
    brier = brier_score_loss(y, p_cal)
    base_rate = y.mean()
    brier_ref = base_rate * (1 - base_rate)
    brier_skill = 1 - brier / brier_ref if brier_ref > 0 else float("nan")
    ece, bins_df = expected_calibration_error(p_cal, y)
    mce = (bins_df["mean_pred"] - bins_df["observed_rate"]).abs().max() if len(bins_df) else float("nan")
    return {
        "auc": auc, "brier": brier, "brier_skill_score": brier_skill,
        "ece": ece, "mce": mce, "bins": bins_df,
    }
