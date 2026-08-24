"""Compare 3 V0 strategy candidates (EMA pullback, breakout, mean-reversion)
with the cost model applied — PROJECT_PLAN.md §14.2 split enforced:

  TRAIN  2023-08 .. 2024-12  -> pick a winner here only
  HOLDOUT 2025-01 .. present -> touch ONCE, after the pick is made

This script reports BOTH so we can see the split, but the discipline is:
whichever strategy wins on TRAIN is the only one that gets judged against
HOLDOUT. Re-running this after seeing HOLDOUT to "adjust" defeats the point.
"""
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals
from src.strategy.breakout import generate_breakout_signals
from src.strategy.mean_reversion import generate_mean_reversion_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs

m15_full = pd.read_parquet("data/raw/BTCUSDT_15m.parquet")
h1 = pd.read_parquet("data/raw/BTCUSDT_1h.parquet")
m1 = pd.read_parquet("data/raw/BTCUSDT_1m.parquet")
funding = pd.read_parquet("data/raw/BTCUSDT_USDT_funding.parquet")

m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
m15_full = m15_full[m15_full["time_utc"] <= m1_end].reset_index(drop=True)

TRAIN_END = pd.Timestamp("2025-01-01", tz="UTC")

STRATEGIES = {
    "EMA_pullback (SL2.5x,ADX35)": lambda m15, f, r: generate_v0_signals(m15, f, r, sl_atr_mult=2.5),
    "Breakout_Donchian20": lambda m15, f, r: generate_breakout_signals(m15, f, r),
    "MeanReversion_fade": lambda m15, f, r: generate_mean_reversion_signals(m15, f, r),
}

REGIME_OVERRIDE = {
    "EMA_pullback (SL2.5x,ADX35)": 35.0,
    "Breakout_Donchian20": 22.0,
    "MeanReversion_fade": 22.0,
}


def run_strategy(name, signal_fn, adx_threshold, m15_slice, h1):
    features = build_features(m15_slice, h1)
    regime = classify_regime(features, adx_threshold=adx_threshold)
    signals = signal_fn(m15_slice, features, regime)
    trade_signals = signals[signals["action"] != "NO_TRADE"].copy()
    if len(trade_signals) == 0:
        return None
    labeled = label_all_signals(trade_signals, m1)
    labeled = labeled.dropna(subset=["label"])
    if len(labeled) == 0:
        return None
    costed = apply_costs(labeled, funding)
    return costed


def summarize(df):
    if df is None or len(df) == 0:
        return {"n": 0, "win_rate": None, "gross_avg_r": None, "net_avg_r": None, "net_pf": None}
    win_rate = (df["net_r_multiple"] > 0).mean()
    gross_avg = df["r_multiple"].mean()
    net_avg = df["net_r_multiple"].mean()
    gross_win = df.loc[df["net_r_multiple"] > 0, "net_r_multiple"].sum()
    gross_loss = -df.loc[df["net_r_multiple"] < 0, "net_r_multiple"].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    return {"n": len(df), "win_rate": win_rate, "gross_avg_r": gross_avg, "net_avg_r": net_avg, "net_pf": pf}


rows = []
for name, fn in STRATEGIES.items():
    adx_th = REGIME_OVERRIDE[name]

    train_slice = m15_full[m15_full["time_utc"] < TRAIN_END].reset_index(drop=True)
    holdout_slice = m15_full[m15_full["time_utc"] >= TRAIN_END].reset_index(drop=True)

    train_result = summarize(run_strategy(name, fn, adx_th, train_slice, h1))
    holdout_result = summarize(run_strategy(name, fn, adx_th, holdout_slice, h1))

    rows.append({"strategy": name, "split": "TRAIN 2023-2024", **train_result})
    rows.append({"strategy": name, "split": "HOLDOUT 2025-2026", **holdout_result})

report = pd.DataFrame(rows)
pd.set_option("display.width", 140)
pd.set_option("display.float_format", lambda x: f"{x:.3f}" if pd.notna(x) else "n/a")
print(report.to_string(index=False))

print("\nDiscipline check: pick the TRAIN winner, judge it ONCE against HOLDOUT.")
print("Do not re-tune parameters after seeing HOLDOUT numbers — that burns the holdout (§14.2).")
