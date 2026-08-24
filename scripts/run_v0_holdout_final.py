"""FINAL holdout check — 2025-2026, touched exactly once, after locking the
config on TRAIN(2023)+VAL(2024) in tune_v0_filters.py.

Locked config: "+both filters" — ADX35, SL2.5x, ATR percentile 20-90%, body ratio > 0.5.
Chosen over the higher-PF ADX45 variant because that one had n=22 on TRAIN,
far below the §14.4 sample-size floor — a better number on an untrustworthy
sample isn't a better strategy.

DO NOT re-run this with different parameters after seeing the result below.
If it fails, the conclusion is "this strategy family doesn't have edge here",
not "let's try another config against this same holdout."
"""
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs

m15_full = pd.read_parquet("data/raw/BTCUSDT_15m.parquet")
h1 = pd.read_parquet("data/raw/BTCUSDT_1h.parquet")
m1 = pd.read_parquet("data/raw/BTCUSDT_1m.parquet")
funding = pd.read_parquet("data/raw/BTCUSDT_USDT_funding.parquet")

m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
m15_full = m15_full[m15_full["time_utc"] <= m1_end].reset_index(drop=True)

HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")
holdout_slice = m15_full[m15_full["time_utc"] >= HOLDOUT_START].reset_index(drop=True)

LOCKED_CONFIG = {"adx": 35, "sl": 2.5, "atr_min": 0.2, "atr_max": 0.9, "body": 0.5}

features = build_features(holdout_slice, h1)
regime = classify_regime(features, adx_threshold=LOCKED_CONFIG["adx"])
signals = generate_v0_signals(
    holdout_slice, features, regime,
    sl_atr_mult=LOCKED_CONFIG["sl"],
    atr_pct_min=LOCKED_CONFIG["atr_min"], atr_pct_max=LOCKED_CONFIG["atr_max"],
    min_body_ratio=LOCKED_CONFIG["body"],
)
trades = signals[signals["action"] != "NO_TRADE"].copy()
labeled = label_all_signals(trades, m1).dropna(subset=["label"])
costed = apply_costs(labeled, funding)

win_rate = (costed["net_r_multiple"] > 0).mean()
net_avg = costed["net_r_multiple"].mean()
gross_win = costed.loc[costed["net_r_multiple"] > 0, "net_r_multiple"].sum()
gross_loss = -costed.loc[costed["net_r_multiple"] < 0, "net_r_multiple"].sum()
pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

print(f"=== FINAL HOLDOUT RESULT (2025-01-01 -> present, config locked, n={len(costed)}) ===")
print(f"Win rate: {win_rate:.1%}")
print(f"Net Avg R: {net_avg:.4f}")
print(f"Net PF: {pf:.3f}")

n = len(costed)
if n < 250:
    print(f"\nWARNING: n={n} is below the §14.4 250-trade floor — treat as inconclusive, not a pass/fail verdict.")
elif pf > 1.10:
    print(f"\nPASS vs §14.3 threshold (PF > 1.10) — but this is one holdout window, not a green light for live.")
else:
    print(f"\nDOES NOT meet §14.3 threshold (PF > 1.10). Net avg R = {net_avg:.4f}.")
