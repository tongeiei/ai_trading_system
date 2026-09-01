"""R2 — Opening Range Breakout + Fib pullback entry, XAU/USD spot.

Hypothesis (docs/research/XAU_REDDIT_SCOUT.md, R2 — the r/Daytrading ORB+Fib post):
  Same opening range as R1 (first N min after London open, 07:00 UTC), but do
  NOT enter on the break. The break only ARMS a direction. Then wait for the
  price to pull back into a Fibonacci retracement of the opening range and
  enter there with a LIMIT fill. The pullback requirement is meant to filter
  out false breakouts (R1's failure mode) and gives a tighter stop.

Per day, LONG side (mirror for SHORT):
  range   = OR_high - OR_low
  break   : first bar that CLOSES > OR_high  -> arm LONG
  fib_lvl = OR_high - fib_ratio * range      (entry, e.g. 0.5 retrace)
  entry   : a later bar whose LOW <= fib_lvl -> fill LONG at fib_lvl
  stop    : OR_low  (sl_distance = fib_lvl - OR_low)
  target  : entry + tp_r_mult * sl_distance
  invalid : if a bar CLOSES < OR_low before the pullback fills -> stand down
  one trade/day, no new arming at/after cutoff_hour.

Entry price is the fib level (limit fill), written into the `close` column
that the harness/triple-barrier treat as the entry price.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def generate_orb_pullback_signals(
    m15: pd.DataFrame,
    or_start_hour: int = 7,
    or_minutes: int = 30,
    cutoff_hour: int = 16,
    fib_ratio: float = 0.5,     # retrace depth into the range for entry
    tp_r_mult: float = 2.0,
    direction: str = "both",    # "both" | "long" | "short"
) -> pd.DataFrame:
    df = m15[["time_utc", "open", "high", "low", "close"]].copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)

    t = df["time_utc"]
    df["date"] = t.dt.date
    mfo = (t.dt.hour - or_start_hour) * 60 + t.dt.minute
    in_or = (mfo >= 0) & (mfo < or_minutes)
    after_or = (mfo >= or_minutes) & (t.dt.hour < cutoff_hour)

    org = df[in_or].groupby("date").agg(or_high=("high", "max"), or_low=("low", "min"))
    df = df.merge(org, on="date", how="left")

    allow_long = direction in ("both", "long")
    allow_short = direction in ("both", "short")

    rows = []
    # per-day stateful scan over the post-OR window
    for date, g in df[after_or & df["or_high"].notna()].groupby("date", sort=False):
        or_high = g["or_high"].iloc[0]
        or_low = g["or_low"].iloc[0]
        rng = or_high - or_low
        if not (rng > 0):
            continue
        armed = None
        fib_lvl = np.nan
        for _, b in g.iterrows():
            if armed is None:
                if allow_long and b["close"] > or_high:
                    armed, fib_lvl = "LONG", or_high - fib_ratio * rng
                elif allow_short and b["close"] < or_low:
                    armed, fib_lvl = "SHORT", or_low + fib_ratio * rng
                continue
            # armed: look for pullback fill, or invalidation
            if armed == "LONG":
                if b["close"] < or_low:            # failed breakout
                    break
                if b["low"] <= fib_lvl:            # limit fill
                    sl_d = fib_lvl - or_low
                    if sl_d > 0:
                        rows.append((b["time_utc"], fib_lvl, "LONG",
                                     or_low, fib_lvl + sl_d * tp_r_mult, sl_d))
                    break
            else:  # SHORT
                if b["close"] > or_high:
                    break
                if b["high"] >= fib_lvl:
                    sl_d = or_high - fib_lvl
                    if sl_d > 0:
                        rows.append((b["time_utc"], fib_lvl, "SHORT",
                                     or_high, fib_lvl - sl_d * tp_r_mult, sl_d))
                    break

    sig = pd.DataFrame(rows, columns=["time_utc", "close", "action", "sl_price", "tp_price", "sl_distance"])
    if sig.empty:
        # keep the contract even with zero trades
        return pd.DataFrame(columns=["time_utc", "close", "action", "sl_price", "tp_price", "sl_distance"])
    return sig
