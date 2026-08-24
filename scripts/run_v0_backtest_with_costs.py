"""P1: same wiring as run_v0_backtest_smoke.py, now with cost model applied
(§8/§14.1) — this is the number that actually matters, not the gross PF."""
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs

m15 = pd.read_parquet("data/raw/BTCUSDT_15m.parquet")
h1 = pd.read_parquet("data/raw/BTCUSDT_1h.parquet")
m1 = pd.read_parquet("data/raw/BTCUSDT_1m.parquet")
funding = pd.read_parquet("data/raw/BTCUSDT_USDT_funding.parquet")

m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)

import sys
sl_mult = float(sys.argv[1]) if len(sys.argv) > 1 else 1.5
adx_threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 22.0

features = build_features(m15, h1)
regime = classify_regime(features, adx_threshold=adx_threshold)
signals = generate_v0_signals(m15, features, regime, sl_atr_mult=sl_mult)
trade_signals = signals[signals["action"] != "NO_TRADE"].copy()
print(f"SL multiplier: {sl_mult}x ATR | ADX threshold: {adx_threshold}")
print(f"Regime distribution:\n{regime.value_counts()}")

labeled = label_all_signals(trade_signals, m1)
labeled = labeled.dropna(subset=["label"])

costed = apply_costs(labeled, funding)

def summarize(df, r_col, label):
    win_rate = (df[r_col] > 0).mean()
    avg_r = df[r_col].mean()
    gross_win = df.loc[df[r_col] > 0, r_col].sum()
    gross_loss = -df.loc[df[r_col] < 0, r_col].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    print(f"\n--- {label} (n={len(df)}) ---")
    print(f"Win rate: {win_rate:.1%} | Avg R: {avg_r:.4f} | PF: {pf:.3f}")
    return avg_r

print(f"n = {len(costed)}")
gross_avg = summarize(costed, "r_multiple", "GROSS (no costs)")
net_avg = summarize(costed, "net_r_multiple", "NET (commission + funding + slippage)")

print(f"\nAvg cost per trade: {gross_avg - net_avg:.4f}R")
print(f"  commission avg: {costed['commission_r'].mean():.4f}R")
print(f"  slippage avg:   {costed['slippage_r'].mean():.4f}R")
print(f"  funding avg:    {costed['funding_r'].mean():.4f}R")

print("\nNet Avg R by year:")
costed["year"] = pd.to_datetime(costed["time_utc"]).dt.year
print(costed.groupby("year")["net_r_multiple"].agg(["mean", "count"]))

print("\nNet Avg R by action (LONG vs SHORT) — funding sign should differ:")
print(costed.groupby("action")[["r_multiple", "net_r_multiple", "funding_r"]].mean())
