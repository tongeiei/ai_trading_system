"""V1: LightGBM probability filter over the V0 candidate setups — PROJECT_PLAN.md §6.3.

V0 (EMA pullback, ADX35/SL2.5x — the config that generalized best across
TRAIN/HOLDOUT, without the extra atr/body filters that didn't hold up)
generates candidate setups. This model learns which of those candidates are
worth taking; it never proposes trades on its own (§0.4 principle).

Target: triple_barrier's `label` column (1 = TP hit first, 0 = SL/loss).
"""
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

FEATURE_COLS = [
    "f01_dist_ema20_atr", "f02_dist_ema50_atr", "f03_h1_trend_atr", "f04_adx14_h1",
    "f05_logret_4", "f06_logret_12", "f07_atr_norm", "f08_atr_percentile",
    "f09_vol_expansion_ratio", "f10_candle_body_ratio",
]
# f12_spread_ratio dropped — always NaN until live execution layer provides it (§4.2 note)

LGBM_PARAMS = dict(
    objective="binary",
    num_leaves=15,
    max_depth=4,
    min_data_in_leaf=100,
    feature_fraction=0.7,
    bagging_fraction=0.8,
    bagging_freq=1,
    lambda_l2=5.0,
    verbosity=-1,
)


def prepare_xy(labeled_trades: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Join labeled trades back to their feature row (by time_utc) and one-hot
    the session column. Drops rows with any NaN feature (warm-up period)."""
    merged = labeled_trades.merge(features, on="time_utc", how="left", suffixes=("", "_feat"))
    session_dummies = pd.get_dummies(merged["session"], prefix="session")
    x = pd.concat([merged[FEATURE_COLS], session_dummies], axis=1)
    y = merged["label"].astype(int)
    valid = x.notna().all(axis=1)
    return x[valid].reset_index(drop=True), y[valid].reset_index(drop=True), merged[valid].reset_index(drop=True)


def train_lgbm(x_train, y_train, x_val, y_val, num_boost_round=500, early_stopping_rounds=30):
    train_set = lgb.Dataset(x_train, label=y_train)
    val_set = lgb.Dataset(x_val, label=y_val, reference=train_set)
    model = lgb.train(
        LGBM_PARAMS, train_set,
        num_boost_round=num_boost_round,
        valid_sets=[val_set],
        callbacks=[lgb.early_stopping(early_stopping_rounds, verbose=False)],
    )
    return model


def train_logreg_baseline(x_train, y_train):
    model = LogisticRegression(max_iter=1000)
    model.fit(x_train, y_train)
    return model


def permutation_test_auc(x_train, y_train, x_val, y_val, x_test, y_test, real_auc: float, n_reps: int = 5, seed: int = 0) -> dict:
    """§20.1 leakage check: shuffle TRAIN labels and RE-FIT (not just re-score) —
    a model fit on label noise should score ~0.50 AUC on real held-out labels.
    If it scores meaningfully above 0.50, some feature is leaking label info.

    n_reps kept small (default 5) since each rep is a full LightGBM fit;
    increase if this needs to be more statistically rigorous later.
    """
    rng = np.random.default_rng(seed)
    y_train_arr = y_train.to_numpy()
    shuffled_aucs = []
    for _ in range(n_reps):
        y_shuf = pd.Series(rng.permutation(y_train_arr), index=y_train.index)
        model = train_lgbm(x_train, y_shuf, x_val, y_val)
        preds = model.predict(x_test, num_iteration=model.best_iteration)
        shuffled_aucs.append(roc_auc_score(y_test, preds))
    return {
        "real_auc": real_auc,
        "shuffled_auc_mean": float(np.mean(shuffled_aucs)),
        "shuffled_auc_std": float(np.std(shuffled_aucs)),
        "n_reps": n_reps,
    }
