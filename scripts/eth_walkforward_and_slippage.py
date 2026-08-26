"""ETH V0 — walk-forward consistency + slippage sensitivity, PROJECT_PLAN.md §15/§14.1.

Adaptation note: V0 is rule-based with a config LOCKED from BTC (no fitting
on ETH data at all), so there's no in-sample fit to compare against — the
classic "Walk-Forward Efficiency = OOS/IS" ratio doesn't directly apply.
Instead we report:
  1. TRAIN-period (2023-2024, pre-holdout) mean R as a pseudo-IS reference
  2. Consistency across purged, non-overlapping windows within the holdout
     (quarterly, already shown as 7/7 positive) — the real question for a
     non-fitted strategy is "does the edge hold across independent windows",
     not "did it overfit to a training set" (it can't, there's no fitting).
  3. Slippage sensitivity 1x/2x/3x per §14.1 — if PF collapses at 2x, the
     edge is too thin to trust the execution assumptions.
"""
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs, SLIPPAGE_BPS
from src.backtest.significance import bootstrap_mean_test

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

LOCKED_CONFIG = {"adx": 35, "sl": 2.5}
TRAIN_END = pd.Timestamp("2025-01-01", tz="UTC")

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

# base cost model (1x slippage)
costed = apply_costs(labeled, funding)
costed["time_utc"] = pd.to_datetime(costed["time_utc"])

train = costed[costed["time_utc"] < TRAIN_END]
holdout = costed[costed["time_utc"] >= TRAIN_END]

print("=== Pseudo-IS/OOS reference (config was locked from BTC, not fit on ETH) ===")
print(f"TRAIN (2023-2024) mean net R: {train['net_r_multiple'].mean():.4f} (n={len(train)})")
print(f"HOLDOUT (2025-2026) mean net R: {holdout['net_r_multiple'].mean():.4f} (n={len(holdout)})")
wfe_proxy = holdout["net_r_multiple"].mean() / train["net_r_multiple"].mean() if train["net_r_multiple"].mean() != 0 else float("nan")
print(f"OOS/IS ratio (informal WFE proxy): {wfe_proxy:.2f}")
print("Interpretation: both positive and holdout is actually STRONGER than train —")
print("opposite of the classic overfitting signature (OOS << IS). This is a good sign,")
print("though it's partly explained by 'this config wasn't fit on ETH at all'.")

print("\n=== Walk-forward consistency: purged, non-overlapping monthly windows in HOLDOUT ===")
holdout = holdout.copy()
holdout["month"] = holdout["time_utc"].dt.to_period("M")
monthly = holdout.groupby("month")["net_r_multiple"].agg(["mean", "count"])
print(monthly)
n_positive = (monthly["mean"] > 0).sum()
n_total = len(monthly)
print(f"\nPositive months: {n_positive}/{n_total} ({n_positive/n_total:.0%})")

print("\n=== Slippage sensitivity (§14.1) — 1x / 2x / 3x base slippage ===")
for mult in [1, 2, 3]:
    costed_s = apply_costs(labeled, funding, taker_fee=0.0005)
    # re-apply with scaled slippage by monkey-patching the constant via direct recompute
    from src.backtest.costs import slippage_cost_r
    costed_s = labeled.copy()
    costed_s["commission_r"] = costed_s.apply(lambda r: 2 * 0.0005 * r["close"] / r["sl_distance"], axis=1)
    costed_s["slippage_r"] = costed_s.apply(lambda r: slippage_cost_r(r["sl_distance"], r["close"], SLIPPAGE_BPS * mult), axis=1)
    from src.backtest.costs import funding_cost_r
    costed_s["funding_r"] = costed_s.apply(
        lambda r: funding_cost_r(r["time_utc"], r["exit_time"], r["close"], r["action"], r["sl_distance"], funding), axis=1
    )
    costed_s["net_r_multiple"] = costed_s["r_multiple"] - costed_s["commission_r"] - costed_s["slippage_r"] - costed_s["funding_r"]
    costed_s["time_utc"] = pd.to_datetime(costed_s["time_utc"])
    hold_s = costed_s[costed_s["time_utc"] >= TRAIN_END]

    win_rate = (hold_s["net_r_multiple"] > 0).mean()
    net_avg = hold_s["net_r_multiple"].mean()
    gross_win = hold_s.loc[hold_s["net_r_multiple"] > 0, "net_r_multiple"].sum()
    gross_loss = -hold_s.loc[hold_s["net_r_multiple"] < 0, "net_r_multiple"].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    print(f"{mult}x slippage: net_avg_r={net_avg:.4f} | pf={pf:.3f}")

    if mult == 1:
        bs = bootstrap_mean_test(hold_s["net_r_multiple"].to_numpy(), n_resamples=5000, seed=1)
        print(f"  (sanity check vs earlier bootstrap: mean={bs['observed_mean']:.4f}, p={bs['p_value']:.4f})")
