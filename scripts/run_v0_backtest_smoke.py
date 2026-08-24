"""P1 backtest wiring check: features -> regime -> V0 signals -> triple-barrier
labels end to end, run on the full 3-year history now that M1 covers it.

Still NOT the full event-driven backtester with cost model from §14.1 — that's
the next step. This tells us whether trade counts/exit distribution are sane
before investing in the cost model + parity tests.
"""
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals
from src.labeling.triple_barrier import label_all_signals

m15 = pd.read_parquet("data/raw/BTCUSDT_15m.parquet")
h1 = pd.read_parquet("data/raw/BTCUSDT_1h.parquet")
m1 = pd.read_parquet("data/raw/BTCUSDT_1m.parquet")

# leave headroom at the end so every signal has a full 12h M1 window to resolve against
m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)
print(f"Window: {m15['time_utc'].min()} -> {m15['time_utc'].max()} ({len(m15)} M15 bars)")

features = build_features(m15, h1)
regime = classify_regime(features)
print("\nRegime distribution:")
print(regime.value_counts())
print((regime.value_counts(normalize=True) * 100).round(1).astype(str) + "%")

signals = generate_v0_signals(m15, features, regime)
trade_signals = signals[signals["action"] != "NO_TRADE"].copy()
print(f"\nCandidate trades: {len(trade_signals)} out of {len(signals)} bars "
      f"({len(trade_signals) / len(signals) * 100:.2f}% of bars)")

print("\nLabeling trades against M1 path data (this takes a bit)...")
labeled = label_all_signals(trade_signals, m1)
labeled = labeled.dropna(subset=["label"])

win_rate = labeled["label"].mean()
avg_r = labeled["r_multiple"].mean()
gross_win = labeled.loc[labeled["r_multiple"] > 0, "r_multiple"].sum()
gross_loss = -labeled.loc[labeled["r_multiple"] < 0, "r_multiple"].sum()
profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")

print(f"\n--- Results (n={len(labeled)}, NO cost model applied yet) ---")
print(f"Win rate: {win_rate:.1%}")
print(f"Avg R: {avg_r:.3f}")
print(f"Profit factor: {profit_factor:.2f}")
print(f"Exit reason breakdown:\n{labeled['exit_reason'].value_counts()}")

# breakdown by year, per §14.3 "3 of 4 quarters positive" style check
labeled["year"] = pd.to_datetime(labeled["time_utc"]).dt.year
print("\nAvg R by year:")
print(labeled.groupby("year")["r_multiple"].agg(["mean", "count"]))

n = len(labeled)
threshold_note = (
    "meets the >=250 trade floor from §14.4 — early signal, not yet conclusive"
    if n >= 250 else
    f"still below the >=250 trade floor from §14.4 (have {n})"
)
print(f"\nNOTE: n={n} {threshold_note}. Cost model (spread/funding/slippage) "
      f"not applied — PF above is optimistic vs. what a real account would see.")
