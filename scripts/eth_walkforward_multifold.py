"""Proper anchored walk-forward, multi-fold — PROJECT_PLAN.md §15.

V0 is rule-based with a LOCKED config (no fitting), so "walk-forward" here
tests something narrower than the classic ML sense but still meaningful:
does the edge hold up consistently across independent, non-overlapping time
windows, or is it concentrated in one lucky stretch?

Folds: anchored quarterly windows across the full 3-year history (not just
the 2025-2026 holdout used for the single-split test) — this uses more of
the data than the single train/holdout split did, which is legitimate here
because the config was locked BEFORE looking at any of this data (from the
original BTC-derived threshold choice), so there's no fitting-to-fold risk.

Embargo: signals whose entry falls within 12h (= max hold period from
triple_barrier.MAX_HOLD_BARS_M1) of a fold boundary are excluded from that
fold, so no trade's outcome depends on data leaking across the boundary.
"""
import numpy as np
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs
from src.backtest.significance import bootstrap_mean_test

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

LOCKED_CONFIG = {"adx": 35, "sl": 2.5}
EMBARGO = pd.Timedelta(hours=12)

m15 = pd.read_parquet("data/raw/ETHUSDT_15m.parquet")
h1 = pd.read_parquet("data/raw/ETHUSDT_1h.parquet")
m1 = pd.read_parquet("data/raw/ETHUSDT_1m.parquet")
funding = pd.read_parquet("data/raw/ETHUSDT_USDT_funding.parquet")

m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)

features = build_features(m15, h1)
regime = classify_regime(features, adx_threshold=LOCKED_CONFIG["adx"])
signals = generate_v0_signals(m15, features, regime, sl_atr_mult=LOCKED_CONFIG["sl"])
trades = signals[signals["action"] != "NO_TRADE"].copy()
labeled = label_all_signals(trades, m1).dropna(subset=["label"])
costed = apply_costs(labeled, funding)
costed["time_utc"] = pd.to_datetime(costed["time_utc"])

# anchored quarterly folds spanning the full history
start = costed["time_utc"].min().to_period("Q").start_time.tz_localize("UTC")
end = costed["time_utc"].max()
fold_bounds = pd.date_range(start, end + pd.Timedelta(days=1), freq="QS", tz="UTC")

rows = []
for i in range(len(fold_bounds) - 1):
    fold_start, fold_end = fold_bounds[i], fold_bounds[i + 1]
    in_fold = (costed["time_utc"] >= fold_start + EMBARGO) & (costed["time_utc"] < fold_end - EMBARGO)
    fold_trades = costed[in_fold]
    if len(fold_trades) == 0:
        rows.append({"fold": f"{fold_start.date()}", "n": 0, "win_rate": None, "net_avg_r": None, "pf": None})
        continue

    win_rate = (fold_trades["net_r_multiple"] > 0).mean()
    net_avg = fold_trades["net_r_multiple"].mean()
    gross_win = fold_trades.loc[fold_trades["net_r_multiple"] > 0, "net_r_multiple"].sum()
    gross_loss = -fold_trades.loc[fold_trades["net_r_multiple"] < 0, "net_r_multiple"].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    rows.append({"fold": f"{fold_start.date()}", "n": len(fold_trades), "win_rate": win_rate, "net_avg_r": net_avg, "pf": pf})

fold_df = pd.DataFrame(rows)
print("=== Walk-forward folds (quarterly, anchored, embargo=12h) ===")
print(fold_df.to_string(index=False))

valid_folds = fold_df[fold_df["n"] >= 20]  # folds with too few trades aren't meaningful to score pos/neg
n_positive = (valid_folds["net_avg_r"] > 0).sum()
n_total = len(valid_folds)
print(f"\nFolds with n>=20: {n_total}, positive: {n_positive} ({n_positive/n_total:.0%})")
print(f"§15 consistency threshold: >=60% of folds positive -> {'PASS' if n_positive/n_total >= 0.6 else 'FAIL'}")

# walk-forward efficiency proxy: variance of net_avg_r across folds vs overall mean
overall_mean = costed["net_r_multiple"].mean()
fold_means = valid_folds["net_avg_r"].dropna()
wf_efficiency = fold_means.min() / overall_mean if overall_mean != 0 else float("nan")
print(f"\nOverall net_avg_r (all folds pooled): {overall_mean:.4f}")
print(f"Worst single fold net_avg_r: {fold_means.min():.4f}")
print(f"Best single fold net_avg_r: {fold_means.max():.4f}")
print(f"Std dev across folds: {fold_means.std():.4f}")

print("\n=== Bootstrap test per fold (n>=20 only) ===")
for _, row in valid_folds.iterrows():
    fold_start_str = row["fold"]
    fold_mask = (costed["time_utc"] >= pd.Timestamp(fold_start_str, tz="UTC")) & \
                (costed["time_utc"] < pd.Timestamp(fold_start_str, tz="UTC") + pd.DateOffset(months=3))
    r_vals = costed.loc[fold_mask, "net_r_multiple"].to_numpy()
    if len(r_vals) < 20:
        continue
    bs = bootstrap_mean_test(r_vals, n_resamples=3000, seed=1)
    sig = "significant" if bs["significant_at_5pct"] else "not significant"
    print(f"{fold_start_str}: n={len(r_vals)}, mean={bs['observed_mean']:.4f}, p={bs['p_value']:.4f} ({sig})")
