"""Phase 6 of docs/PLAN_CUSTOM.md — trade duration analysis, research
question 7.

Measures MFE (max favorable excursion), MAE (max adverse excursion), time
to TP, time to SL, and mark-to-market return at fixed checkpoints
(1h/2h/4h/8h/12h) for the V0 baseline's trades (same control used in every
prior phase, research pool only). Determines whether valid setups tend to
resolve quickly — informational only; per PLAN_CUSTOM, the live 12h
MAX_HOLD_BARS_M1 timeout is NOT changed here regardless of what this shows.

Does not modify src/strategy/v0_rules.py or src/live/position_timeout.py.
"""
import numpy as np
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

LOCKED_V0_CONFIG = {"adx": 35, "sl": 2.5}
SACRED_HOLDOUT_START = pd.Timestamp("2026-07-01", tz="UTC")
MAX_HOLD_BARS_M1 = 12 * 60
CHECKPOINTS_MIN = [60, 120, 240, 480, 720]  # 1h, 2h, 4h, 8h, 12h


def load_data():
    m15 = pd.read_parquet("data/raw/ETHUSDT_15m.parquet")
    h1 = pd.read_parquet("data/raw/ETHUSDT_1h.parquet")
    m1 = pd.read_parquet("data/raw/ETHUSDT_1m.parquet")
    return m15, h1, m1


def analyze_trade(action, entry_time, entry_price, sl_price, tp_price, m1, m1_times):
    start_idx = m1_times.searchsorted(entry_time, side="right")
    end_idx = min(start_idx + MAX_HOLD_BARS_M1, len(m1))
    window = m1.iloc[start_idx:end_idx]
    if window.empty:
        return None

    sl_distance = abs(entry_price - sl_price)
    sign = 1 if action == "LONG" else -1

    highs, lows, closes = window["high"].to_numpy(), window["low"].to_numpy(), window["close"].to_numpy()
    times = window["time_utc"].to_numpy()

    if action == "LONG":
        hit_sl = lows <= sl_price
        hit_tp = highs >= tp_price
    else:
        hit_sl = highs >= sl_price
        hit_tp = lows <= tp_price

    exit_idx = None
    exit_reason = "TIMEOUT"
    for i in range(len(window)):
        if hit_sl[i] and hit_tp[i]:
            exit_idx, exit_reason = i, "SL"  # conservative, matches triple_barrier.py
            break
        if hit_sl[i]:
            exit_idx, exit_reason = i, "SL"
            break
        if hit_tp[i]:
            exit_idx, exit_reason = i, "TP"
            break
    if exit_idx is None:
        exit_idx = len(window) - 1
        exit_reason = "TIMEOUT"

    path = window.iloc[:exit_idx + 1]
    favorable_prices = path["high"] if action == "LONG" else path["low"]
    adverse_prices = path["low"] if action == "LONG" else path["high"]
    # apply sign BEFORE taking max/min — for SHORT, "favorable" means price going
    # down, so the max R-in-favor comes from the lowest price, not literally max(price)
    favorable_r_series = sign * (favorable_prices - entry_price) / sl_distance
    adverse_r_series = sign * (adverse_prices - entry_price) / sl_distance
    mfe = favorable_r_series.max()
    mae = adverse_r_series.min()  # negative = adverse

    exit_time = pd.Timestamp(times[exit_idx])
    minutes_to_exit = (exit_time - entry_time).total_seconds() / 60.0

    r_final = sign * (closes[exit_idx] - entry_price) / sl_distance
    if exit_reason == "TP":
        r_final = sign * (tp_price - entry_price) / sl_distance
    elif exit_reason == "SL":
        r_final = sign * (sl_price - entry_price) / sl_distance

    checkpoint_r = {}
    for cp_min in CHECKPOINTS_MIN:
        if minutes_to_exit <= cp_min:
            checkpoint_r[cp_min] = r_final  # already closed by this checkpoint
        else:
            cp_idx = min(int(cp_min) - 1, len(window) - 1)
            checkpoint_r[cp_min] = sign * (closes[cp_idx] - entry_price) / sl_distance

    return {
        "exit_reason": exit_reason, "minutes_to_exit": minutes_to_exit,
        "mfe_r": mfe, "mae_r": mae, "r_final": r_final,
        **{f"r_at_{m}min": v for m, v in checkpoint_r.items()},
    }


def main():
    m15, h1, m1 = load_data()
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)
    pool_mask = m15["time_utc"] < SACRED_HOLDOUT_START
    m15_pool = m15[pool_mask].reset_index(drop=True)
    h1_pool = h1[h1["time_utc"] < SACRED_HOLDOUT_START].reset_index(drop=True)

    features = build_features(m15_pool, h1_pool)
    regime = classify_regime(features, adx_threshold=LOCKED_V0_CONFIG["adx"])
    signals = generate_v0_signals(m15_pool, features, regime, sl_atr_mult=LOCKED_V0_CONFIG["sl"])
    trades = signals[signals["action"] != "NO_TRADE"].reset_index(drop=True)
    print(f"V0 baseline trades to analyze: {len(trades)}")

    m1_sorted = m1.sort_values("time_utc").reset_index(drop=True)
    m1_times = m1_sorted["time_utc"]

    results = []
    for _, t in trades.iterrows():
        r = analyze_trade(t["action"], t["time_utc"], t["close"], t["sl_price"], t["tp_price"], m1_sorted, m1_times)
        if r is not None:
            r["action"] = t["action"]
            results.append(r)

    df = pd.DataFrame(results)
    print(f"Analyzed: {len(df)} trades\n")

    print("=== Exit reason breakdown ===")
    print(df["exit_reason"].value_counts())
    print(f"\nAs %: \n{(df['exit_reason'].value_counts(normalize=True) * 100).round(1)}")

    print("\n=== Time to exit, by exit reason (minutes) ===")
    print(df.groupby("exit_reason")["minutes_to_exit"].describe()[["count", "mean", "50%", "min", "max"]])

    print("\n=== Time to TP specifically (hours) ===")
    tp_hours = df.loc[df["exit_reason"] == "TP", "minutes_to_exit"] / 60
    print(tp_hours.describe())

    print("\n=== Time to SL specifically (hours) ===")
    sl_hours = df.loc[df["exit_reason"] == "SL", "minutes_to_exit"] / 60
    print(sl_hours.describe())

    print("\n=== MFE / MAE (R units) ===")
    print(df[["mfe_r", "mae_r"]].describe())
    print(f"\nMFE by exit reason:\n{df.groupby('exit_reason')['mfe_r'].mean()}")
    print(f"\nMAE by exit reason:\n{df.groupby('exit_reason')['mae_r'].mean()}")

    # trades that hit TP: how much MFE beyond the 2R target did they show, before pulling back to exit at 2R?
    tp_trades = df[df["exit_reason"] == "TP"]
    print(f"\nMean MFE for TP trades: {tp_trades['mfe_r'].mean():.3f}R (TP itself = 2.0R, so overshoot = "
          f"{tp_trades['mfe_r'].mean() - 2.0:.3f}R on average)")

    sl_trades = df[df["exit_reason"] == "SL"]
    print(f"Mean MFE for SL trades (how far favorable did losers get before reversing to SL): "
          f"{sl_trades['mfe_r'].mean():.3f}R")

    print("\n=== Mark-to-market return at fixed checkpoints (mean R, all trades) ===")
    for cp_min, label in zip(CHECKPOINTS_MIN, ["1h", "2h", "4h", "8h", "12h"]):
        col = f"r_at_{cp_min}min"
        print(f"{label:>4}: mean={df[col].mean():.4f}R  median={df[col].median():.4f}R  "
              f"%positive={100*(df[col] > 0).mean():.1f}%")

    print(f"\nFinal (up to 12h timeout) mean R: {df['r_final'].mean():.4f}R  "
          f"median={df['r_final'].median():.4f}R")

    # resolution speed: what fraction of trades are DONE (TP or SL, not timeout) by each checkpoint?
    print("\n=== % of trades already resolved (TP/SL hit, not still open) by each checkpoint ===")
    for cp_min, label in zip(CHECKPOINTS_MIN, ["1h", "2h", "4h", "8h", "12h"]):
        resolved = (df["minutes_to_exit"] <= cp_min) & (df["exit_reason"] != "TIMEOUT")
        print(f"{label:>4}: {100*resolved.mean():.1f}% resolved")

    df.to_csv("docs/research/artifacts/phase6_duration_raw.csv", index=False)
    print("\nSaved: docs/research/artifacts/phase6_duration_raw.csv")


if __name__ == "__main__":
    main()
