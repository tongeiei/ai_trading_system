"""V1: train LightGBM probability filter over V0 candidates, calibrate,
evaluate, and compare against V0 baseline on the SAME final holdout used
in run_v0_holdout_final.py — the Phase P5 gate decision (§P5).

Split (adapted from §14.2's 4-way split to fit 3 years of data):
  TRAIN        2023-08 .. 2024-12  (fit LightGBM)
  CALIBRATION  2025-01 .. 2025-06  (fit isotonic — disjoint from TRAIN)
  VALIDATION   2025-07 .. 2025-12  (permutation test dataset)
  HOLDOUT      2026-01 .. present  (touch once — same window as V0's final holdout)
"""
import numpy as np
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs
from src.models.train import FEATURE_COLS, prepare_xy, train_lgbm, train_logreg_baseline, permutation_test_auc
from src.models.calibrate import fit_isotonic, evaluate_calibration

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

# --- load data ---
m15_full = pd.read_parquet("data/raw/BTCUSDT_15m.parquet")
h1 = pd.read_parquet("data/raw/BTCUSDT_1h.parquet")
m1 = pd.read_parquet("data/raw/BTCUSDT_1m.parquet")
funding = pd.read_parquet("data/raw/BTCUSDT_USDT_funding.parquet")

m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
m15_full = m15_full[m15_full["time_utc"] <= m1_end].reset_index(drop=True)

# --- V0 candidate generator: the config that generalized best (§P1 conclusion) ---
V0_CONFIG = {"adx": 35, "sl": 2.5}

features_full = build_features(m15_full, h1)
regime_full = classify_regime(features_full, adx_threshold=V0_CONFIG["adx"])
signals_full = generate_v0_signals(m15_full, features_full, regime_full, sl_atr_mult=V0_CONFIG["sl"])
all_candidates = signals_full[signals_full["action"] != "NO_TRADE"].copy()

print(f"Total V0 candidates across full history: {len(all_candidates)}")
labeled_full = label_all_signals(all_candidates, m1).dropna(subset=["label"])
costed_full = apply_costs(labeled_full, funding)
print(f"Labeled + costed: {len(costed_full)}")

# --- splits ---
SPLITS = {
    "train": (pd.Timestamp("2023-08-25", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC")),
    "cal":   (pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-07-01", tz="UTC")),
    "val":   (pd.Timestamp("2025-07-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC")),
    "holdout": (pd.Timestamp("2026-01-01", tz="UTC"), pd.Timestamp("2100-01-01", tz="UTC")),
}


def slice_split(df, name):
    start, end = SPLITS[name]
    return df[(df["time_utc"] >= start) & (df["time_utc"] < end)].reset_index(drop=True)


costed_full["time_utc"] = pd.to_datetime(costed_full["time_utc"])

x_all, y_all, merged_all = prepare_xy(costed_full, features_full)
merged_all["time_utc"] = pd.to_datetime(merged_all["time_utc"])

def split_xy(name):
    mask = merged_all["time_utc"].apply(lambda t: SPLITS[name][0] <= t < SPLITS[name][1])
    return x_all[mask].reset_index(drop=True), y_all[mask].reset_index(drop=True), merged_all[mask].reset_index(drop=True)

x_train, y_train, m_train = split_xy("train")
x_cal, y_cal, m_cal = split_xy("cal")
x_val, y_val, m_val = split_xy("val")
x_hold, y_hold, m_hold = split_xy("holdout")

print(f"\nSplit sizes -> train:{len(x_train)} cal:{len(x_cal)} val:{len(x_val)} holdout:{len(x_hold)}")

if len(x_train) < 200 or len(x_cal) < 50 or len(x_hold) < 50:
    print("\nWARNING: one or more splits are very small — treat all downstream numbers as exploratory.")

# --- train ---
print("\n--- Training LightGBM ---")
lgbm_model = train_lgbm(x_train, y_train, x_val, y_val)
p_raw_val = lgbm_model.predict(x_val, num_iteration=lgbm_model.best_iteration)

print("--- Training Logistic Regression baseline ---")
logreg_model = train_logreg_baseline(x_train, y_train)
from sklearn.metrics import roc_auc_score
logreg_auc_val = roc_auc_score(y_val, logreg_model.predict_proba(x_val)[:, 1])
lgbm_auc_val = roc_auc_score(y_val, p_raw_val)
print(f"LightGBM AUC (val): {lgbm_auc_val:.4f} | LogReg AUC (val): {logreg_auc_val:.4f}")

if lgbm_auc_val - logreg_auc_val < 0.03:
    print("NOTE: LightGBM does not beat LogReg by >=3% AUC on val — §6.3 says prefer LogReg for robustness.")

# --- calibrate on CAL fold (disjoint from train) ---
p_raw_cal = lgbm_model.predict(x_cal, num_iteration=lgbm_model.best_iteration)
calibrator = fit_isotonic(p_raw_cal, y_cal.to_numpy())

# --- evaluate calibration on HOLDOUT (final, touched once) ---
p_raw_hold = lgbm_model.predict(x_hold, num_iteration=lgbm_model.best_iteration)
p_cal_hold = calibrator.predict(p_raw_hold)

print("\n--- Calibration evaluation on HOLDOUT ---")
eval_result = evaluate_calibration(p_cal_hold, y_hold.to_numpy())
print(f"AUC: {eval_result['auc']:.4f} | Brier: {eval_result['brier']:.4f} | "
      f"Brier Skill Score: {eval_result['brier_skill_score']:.4f} | ECE: {eval_result['ece']:.4f} | MCE: {eval_result['mce']:.4f}")
print("\nCalibration bins (n<30 = untrustworthy per §7.3):")
print(eval_result["bins"].to_string(index=False))

# --- permutation test (§20.1), run on val/holdout split for speed ---
print("\n--- Permutation test (retrain on shuffled train labels x5, score on holdout) ---")
perm = permutation_test_auc(x_train, y_train, x_val, y_val, x_hold, y_hold, real_auc=eval_result["auc"], n_reps=5)
print(perm)
if perm["shuffled_auc_mean"] > 0.55:
    print("WARNING: shuffled-label AUC is meaningfully above 0.50 — possible leakage, investigate before trusting real_auc.")
else:
    print("OK: shuffled-label AUC is near 0.50, no evidence of leakage.")

# --- P5 gate: V1 (ML-filtered) vs V0 (unfiltered) net R on the SAME holdout trades ---
EV_THRESHOLD_PROXY = 0.5  # p_cal above this = "take it" (placeholder go/no-go; §8.2 EV formula needs avg win/loss estimated from cal fold, done below)

avg_win_r = m_cal.loc[y_cal == 1, "net_r_multiple"].mean()
avg_loss_r = -m_cal.loc[y_cal == 0, "net_r_multiple"].mean()
print(f"\nFrom CAL fold: avg_win_r={avg_win_r:.3f}, avg_loss_r={avg_loss_r:.3f}")

ev_hold = p_cal_hold * avg_win_r - (1 - p_cal_hold) * avg_loss_r
take_mask = ev_hold >= 0.15  # §8.2 decision rule threshold

v0_net_r = m_hold["net_r_multiple"].mean()
v1_net_r = m_hold.loc[take_mask, "net_r_multiple"].mean() if take_mask.sum() > 0 else float("nan")

print(f"\n=== P5 GATE: HOLDOUT comparison (same trade universe, n={len(m_hold)}) ===")
print(f"V0 (take everything):        net_avg_r = {v0_net_r:.4f}, n = {len(m_hold)}")
print(f"V1 (EV>=0.15R filter only):  net_avg_r = {v1_net_r:.4f}, n = {int(take_mask.sum())}")

if take_mask.sum() >= 30:
    improvement = v1_net_r - v0_net_r
    print(f"\nImprovement: {improvement:+.4f}R (needs >= +0.10R AND paired bootstrap p<0.05 per §P5 to justify keeping ML)")
else:
    print(f"\nn={int(take_mask.sum())} too small on holdout to draw a P5 conclusion — inconclusive by sample size alone.")
