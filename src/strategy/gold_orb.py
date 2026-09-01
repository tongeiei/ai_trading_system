"""R1 — Opening Range Breakout (ORB) for XAU/USD spot.

Hypothesis (docs/research/XAU_REDDIT_SCOUT.md, R1):
  Define the opening range = first N minutes after the London open (07:00 UTC).
  The first bar that CLOSES beyond that range gives direction:
    close > OR_high  -> LONG
    close < OR_low   -> SHORT
  Stop = opposite side of the opening range (natural invalidation).
  Target = tp_r_mult * risk (R-based).
  One trade per day, first breakout wins; no new entries after `cutoff_hour`.

Mechanism (why it might pay, per the r/algotrading "who pays you" test):
  the OR captures overnight/Asian inventory; the London session forces that
  inventory to resolve, and participants who faded the open get run over on
  the break. Whether that survives cost is exactly what the backtest decides.

Produces the harness SignalFn contract:
  time_utc, close, action, sl_price, tp_price, sl_distance
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def generate_orb_signals(
    m15: pd.DataFrame,
    or_start_hour: int = 7,      # London open, UTC
    or_minutes: int = 30,        # opening-range length
    cutoff_hour: int = 16,       # no new entries at/after this UTC hour (NY session on)
    tp_r_mult: float = 2.0,
    direction: str = "both",     # "both" | "long" | "short"
) -> pd.DataFrame:
    """Vectorized-per-day ORB. m15 needs [time_utc, open, high, low, close]."""
    df = m15[["time_utc", "open", "high", "low", "close"]].copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)

    t = df["time_utc"]
    df["date"] = t.dt.date
    minutes_from_open = (t.dt.hour - or_start_hour) * 60 + t.dt.minute

    in_or = (minutes_from_open >= 0) & (minutes_from_open < or_minutes)
    after_or = (minutes_from_open >= or_minutes) & (t.dt.hour < cutoff_hour)

    # opening range per day
    org = df[in_or].groupby("date").agg(or_high=("high", "max"), or_low=("low", "min"))
    df = df.merge(org, on="date", how="left")

    long_break = after_or & df["or_high"].notna() & (df["close"] > df["or_high"])
    short_break = after_or & df["or_low"].notna() & (df["close"] < df["or_low"])
    if direction == "long":
        short_break = short_break & False
    elif direction == "short":
        long_break = long_break & False

    df["is_break"] = long_break | short_break
    # keep only the FIRST breakout bar per day
    df["break_rank"] = df[df["is_break"]].groupby("date").cumcount().reindex(df.index)
    first_break = df["is_break"] & (df["break_rank"] == 0)

    action = pd.Series("NO_TRADE", index=df.index)
    action[first_break & long_break] = "LONG"
    action[first_break & short_break] = "SHORT"

    entry = df["close"]
    sl_price = pd.Series(np.nan, index=df.index, dtype="float64")
    sl_price[action == "LONG"] = df["or_low"][action == "LONG"]
    sl_price[action == "SHORT"] = df["or_high"][action == "SHORT"]
    sl_distance = (entry - sl_price).abs()

    # guard degenerate ranges (entry landed exactly on the stop side)
    bad = (action != "NO_TRADE") & ~(sl_distance > 0)
    action[bad] = "NO_TRADE"

    tp_price = pd.Series(np.nan, index=df.index, dtype="float64")
    is_long = action == "LONG"
    is_short = action == "SHORT"
    tp_price[is_long] = entry[is_long] + sl_distance[is_long] * tp_r_mult
    tp_price[is_short] = entry[is_short] - sl_distance[is_short] * tp_r_mult

    out = pd.DataFrame({
        "time_utc": df["time_utc"],
        "close": entry,
        "action": action,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "sl_distance": sl_distance,
    })
    return out
