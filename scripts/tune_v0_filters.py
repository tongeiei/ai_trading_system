"""Tune EMA-pullback quality filters on TRAIN (2023) + VALIDATE on 2024 only.
2025-2026 stays untouched until a config is locked in — see run_v0_holdout_final.py.
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

TRAIN_START = pd.Timestamp("2023-08-25", tz="UTC")
TRAIN_END = pd.Timestamp("2024-01-01", tz="UTC")
VAL_END = pd.Timestamp("2025-01-01", tz="UTC")

train_slice = m15_full[(m15_full["time_utc"] >= TRAIN_START) & (m15_full["time_utc"] < TRAIN_END)].reset_index(drop=True)
val_slice = m15_full[(m15_full["time_utc"] >= TRAIN_END) & (m15_full["time_utc"] < VAL_END)].reset_index(drop=True)

CONFIGS = [
    {"name": "baseline (ADX35, SL2.5x, no filter)", "adx": 35, "sl": 2.5, "atr_min": 0.0, "atr_max": 1.0, "body": 0.0},
    {"name": "+vol filter (ATR 20-90pct)",           "adx": 35, "sl": 2.5, "atr_min": 0.2, "atr_max": 0.9, "body": 0.0},
    {"name": "+body filter (>0.5)",                  "adx": 35, "sl": 2.5, "atr_min": 0.0, "atr_max": 1.0, "body": 0.5},
    {"name": "+both filters",                        "adx": 35, "sl": 2.5, "atr_min": 0.2, "atr_max": 0.9, "body": 0.5},
    {"name": "+both, stricter ADX45",                "adx": 45, "sl": 2.5, "atr_min": 0.2, "atr_max": 0.9, "body": 0.5},
]


def run(cfg, m15_slice):
    features = build_features(m15_slice, h1)
    regime = classify_regime(features, adx_threshold=cfg["adx"])
    signals = generate_v0_signals(
        m15_slice, features, regime,
        sl_atr_mult=cfg["sl"], atr_pct_min=cfg["atr_min"], atr_pct_max=cfg["atr_max"], min_body_ratio=cfg["body"],
    )
    trades = signals[signals["action"] != "NO_TRADE"].copy()
    if len(trades) == 0:
        return {"n": 0, "net_avg_r": None, "net_pf": None}
    labeled = label_all_signals(trades, m1).dropna(subset=["label"])
    if len(labeled) == 0:
        return {"n": 0, "net_avg_r": None, "net_pf": None}
    costed = apply_costs(labeled, funding)
    gross_win = costed.loc[costed["net_r_multiple"] > 0, "net_r_multiple"].sum()
    gross_loss = -costed.loc[costed["net_r_multiple"] < 0, "net_r_multiple"].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    return {"n": len(costed), "net_avg_r": costed["net_r_multiple"].mean(), "net_pf": pf}


rows = []
for cfg in CONFIGS:
    train_res = run(cfg, train_slice)
    val_res = run(cfg, val_slice)
    rows.append({"config": cfg["name"],
                  "train_n": train_res["n"], "train_net_r": train_res["net_avg_r"], "train_pf": train_res["net_pf"],
                  "val_n": val_res["n"], "val_net_r": val_res["net_avg_r"], "val_pf": val_res["net_pf"]})

report = pd.DataFrame(rows)
pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.3f}" if pd.notna(x) else "n/a")
print(f"TRAIN: {TRAIN_START.date()} -> {TRAIN_END.date()} | VALIDATE: {TRAIN_END.date()} -> {VAL_END.date()}")
print(f"(2025-2026 is NOT touched here — that's the final holdout, see run_v0_holdout_final.py)\n")
print(report.to_string(index=False))
print(f"\nTested {len(CONFIGS)} configs so far — running total for §20.1 over-optimization tracking.")
