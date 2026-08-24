"""Bootstrap significance test on ETH holdout net R — is +0.152R distinguishable
from zero, or could it be noise from a lucky 786-trade sample?"""
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs
from src.backtest.significance import bootstrap_mean_test

LOCKED_CONFIG = {"adx": 35, "sl": 2.5}
HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")

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

holdout = costed[costed["time_utc"] >= HOLDOUT_START]
print(f"ETH holdout n={len(holdout)}")

result = bootstrap_mean_test(holdout["net_r_multiple"].to_numpy(), n_resamples=10_000, seed=42)
print(f"\nObserved mean net R: {result['observed_mean']:.4f}")
print(f"95% CI: [{result['ci_95_lo']:.4f}, {result['ci_95_hi']:.4f}]")
print(f"p-value: {result['p_value']:.4f}")
print(f"Significant at 5%: {result['significant_at_5pct']}")

if result["significant_at_5pct"]:
    print("\n=> The positive mean survives bootstrap resampling — not obviously noise from a lucky sample.")
    print("   Still only ONE holdout window on ONE symbol — walk-forward across more windows needed before trusting this for live.")
else:
    print("\n=> Cannot rule out that the positive mean is noise. Do not treat ETH as a proven edge.")
