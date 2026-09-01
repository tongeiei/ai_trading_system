"""Smoke test for the gold backtest harness (src/backtest/gold_harness.py).

Proves the whole pipe runs end-to-end on XAU/USD spot data with a TRIVIAL
placeholder rule. This is NOT a validated hypothesis and its numbers mean
nothing about tradeability — it exists only to exercise load -> features ->
signals -> triple-barrier -> costs -> walk-forward and print a report.

Real hypotheses (R1 ORB, R8 post-liquidation reversal, ... see
docs/research/XAU_REDDIT_SCOUT.md) get their own signal_fn + script.

Usage:
    .venv/bin/python scripts/run_gold_backtest_smoke.py            # last ~3y (fast)
    .venv/bin/python scripts/run_gold_backtest_smoke.py --full     # full 20y
"""
import sys

import numpy as np
import pandas as pd

from src.backtest.gold_harness import load_spec, run_gold_backtest


def placeholder_london_open_long(m15: pd.DataFrame, h1: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """PLACEHOLDER — go LONG on the 07:00 UTC (London open) M15 bar each day.
    SL = 1.5*ATR, TP = 2R. Trivial by design; just makes the pipe produce trades.
    """
    df = m15[["time_utc", "close"]].reset_index(drop=True).copy()
    atr = (features["f07_atr_norm"] * m15["close"]).reset_index(drop=True)

    is_entry = (df["time_utc"].dt.hour == 7) & (df["time_utc"].dt.minute == 0)
    sl_distance = 1.5 * atr

    df["action"] = np.where(is_entry & atr.notna() & (sl_distance > 0), "LONG", "NO_TRADE")
    df["sl_distance"] = sl_distance
    df["sl_price"] = df["close"] - sl_distance
    df["tp_price"] = df["close"] + sl_distance * 2.0
    df.loc[df["action"] == "NO_TRADE", ["sl_price", "tp_price"]] = np.nan
    return df


def main() -> None:
    full = "--full" in sys.argv
    start = None if full else "2022-08-01"
    spec = load_spec()
    print(f"cost assumptions (bps/side): spread={spec['costs']['spread_bps_per_side']} "
          f"slippage={spec['costs']['slippage_bps_per_side']} "
          f"commission={spec['costs']['commission_bps_per_side']}  (no funding — spot)")
    run_gold_backtest(placeholder_london_open_long, spec=spec, start=start)
    print("\n[smoke] pipe OK — plug real R-hypotheses in via their own signal_fn.")


if __name__ == "__main__":
    main()
