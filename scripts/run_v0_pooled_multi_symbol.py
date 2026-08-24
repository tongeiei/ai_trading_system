"""Pooled multi-symbol V0 backtest — BTC + ETH + SOL + BNB, SAME locked config
(ADX35, SL2.5x) as run_v0_holdout_final.py. No re-tuning per symbol — that
would just reintroduce the multiple-comparison problem discussed with the user.

TRAIN 2023-08..2024-12 | HOLDOUT 2025-01..present, matching the BTC-only test.
"""
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
LOCKED_CONFIG = {"adx": 35, "sl": 2.5}
HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")


def load_and_run(symbol: str) -> pd.DataFrame:
    m15 = pd.read_parquet(f"data/raw/{symbol}_15m.parquet")
    h1 = pd.read_parquet(f"data/raw/{symbol}_1h.parquet")
    m1 = pd.read_parquet(f"data/raw/{symbol}_1m.parquet")
    funding = pd.read_parquet(f"data/raw/{symbol}_USDT_funding.parquet")

    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)

    features = build_features(m15, h1)
    regime = classify_regime(features, adx_threshold=LOCKED_CONFIG["adx"])
    signals = generate_v0_signals(m15, features, regime, sl_atr_mult=LOCKED_CONFIG["sl"])
    trades = signals[signals["action"] != "NO_TRADE"].copy()
    if len(trades) == 0:
        return pd.DataFrame()

    labeled = label_all_signals(trades, m1).dropna(subset=["label"])
    if len(labeled) == 0:
        return pd.DataFrame()

    costed = apply_costs(labeled, funding)
    costed["symbol"] = symbol
    return costed


def summarize(df: pd.DataFrame, label: str):
    if len(df) == 0:
        print(f"{label}: no trades")
        return
    win_rate = (df["net_r_multiple"] > 0).mean()
    net_avg = df["net_r_multiple"].mean()
    gross_win = df.loc[df["net_r_multiple"] > 0, "net_r_multiple"].sum()
    gross_loss = -df.loc[df["net_r_multiple"] < 0, "net_r_multiple"].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    print(f"{label}: n={len(df)} | win_rate={win_rate:.1%} | net_avg_r={net_avg:.4f} | pf={pf:.3f}")


all_results = []
for sym in SYMBOLS:
    print(f"Running {sym}...")
    res = load_and_run(sym)
    all_results.append(res)

pooled = pd.concat(all_results, ignore_index=True)
pooled["time_utc"] = pd.to_datetime(pooled["time_utc"])

print("\n=== Per-symbol breakdown (full history) ===")
for sym in SYMBOLS:
    summarize(pooled[pooled["symbol"] == sym], sym)

print("\n=== Per-symbol HOLDOUT only (2025-2026, untouched split like BTC test) ===")
holdout = pooled[pooled["time_utc"] >= HOLDOUT_START]
for sym in SYMBOLS:
    summarize(holdout[holdout["symbol"] == sym], sym)

print("\n=== POOLED across all 4 symbols, HOLDOUT only ===")
summarize(holdout, "POOLED (BTC+ETH+SOL+BNB)")

print("\n=== POOLED, full history (train+holdout combined, for reference only) ===")
summarize(pooled, "POOLED full history")
