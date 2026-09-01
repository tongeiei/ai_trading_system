"""R8 — Post-liquidation reversal (capitulation fade), XAU/USD spot.

Hypothesis (docs/research/R8_PLAN.md, mechanism: forced-seller/liquidation
overshoot). On m15:

  atr        = ATR(atr_len) computed as of the close BEFORE the signal candle
               (shift(1) — the capitulation candle's own huge range must not
               inflate the threshold that flags it)
  range_i    = high_i - low_i
  capitulation DOWN (candle i, ARMS long-reversal):
    close_i < open_i                              (red)
    range_i >= k_capit * atr                       (abnormally violent)
    (close_i - low_i) <= close_frac * range_i      (closes near the low)
  exhaustion confirm (candle i+1 .. i+M):
    first candle j with range_j < range_i * shrink   OR  close_j > open_j
    -> enter LONG at close_j (the confirm bar's own close, not a future bar)
    sl_price    = min(low, i..j) - buf * atr
    sl_distance = entry - sl_price   (> 0)
    tp_price    = entry + tp_r_mult * sl_distance
  invalidate: no confirm within M bars after i -> stand down, no trade
  mirror for capitulation UP -> SHORT
  session: only arm if candle i's hour is in the high_liquidity window
           (LONDON 8-13, OVERLAP 13-16, NY 16-21 UTC)
  one trade at a time (no overlapping arms) — after a resolution (fill or
  invalidation) the scan resumes at the next unused bar.

`baseline` mode (for the R8 red-flag check, docs/research/R8_PLAN.md §6a):
  fade the capitulation candle itself, entering at its own close, WITHOUT
  waiting for an exhaustion confirm. Same k_capit/close_frac/session filter,
  same SL/TP construction (buf off the capitulation candle's own low/high).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HIGH_LIQ_HOURS = range(8, 21)  # LONDON(8-13) + OVERLAP(13-16) + NY(16-21) UTC


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def generate_r8_signals(
    m15: pd.DataFrame,
    atr_len: int = 14,
    k_capit: float = 2.5,
    close_frac: float = 0.35,
    shrink: float = 0.7,
    buf: float = 0.1,
    M: int = 3,
    tp_r_mult: float = 1.5,
    direction: str = "both",       # "both" | "long"
    session_filter: bool = True,
    baseline: bool = False,        # True -> naive fade-and-enter-immediately baseline
) -> pd.DataFrame:
    df = m15[["time_utc", "open", "high", "low", "close"]].copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)

    df["atr"] = _atr(df, atr_len).shift(1)  # as-of PRIOR close: no look-ahead
    df["range"] = df["high"] - df["low"]
    df["is_red"] = df["close"] < df["open"]
    df["is_green"] = df["close"] > df["open"]
    df["hour"] = df["time_utc"].dt.hour

    o, h, l, c = df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    atr = df["atr"].to_numpy()
    rng = df["range"].to_numpy()
    is_red = df["is_red"].to_numpy()
    is_green = df["is_green"].to_numpy()
    hour = df["hour"].to_numpy()
    t = df["time_utc"].to_numpy()

    allow_long = direction in ("both", "long")
    allow_short = direction in ("both",)  # "long" excludes shorts; both is the only short-enabling option here

    n = len(df)
    rows = []
    i = 0
    while i < n:
        a = atr[i]
        if not (a > 0) or np.isnan(a):
            i += 1
            continue
        if session_filter and hour[i] not in HIGH_LIQ_HOURS:
            i += 1
            continue

        r_i = rng[i]
        cap_down = (
            allow_long and is_red[i] and r_i >= k_capit * a
            and (c[i] - l[i]) <= close_frac * r_i
        )
        cap_up = (
            allow_short and (not is_red[i]) and is_green[i] and r_i >= k_capit * a
            and (h[i] - c[i]) <= close_frac * r_i
        )

        if not (cap_down or cap_up):
            i += 1
            continue

        if baseline:
            # naive: enter at the capitulation candle's own close, no confirm wait
            if cap_down:
                entry = c[i]
                sl = l[i] - buf * a
                sl_d = entry - sl
                if sl_d > 0:
                    rows.append((t[i], entry, "LONG", sl, entry + tp_r_mult * sl_d, sl_d))
            else:
                entry = c[i]
                sl = h[i] + buf * a
                sl_d = sl - entry
                if sl_d > 0:
                    rows.append((t[i], entry, "SHORT", sl, entry - tp_r_mult * sl_d, sl_d))
            i += 1
            continue

        # wait for exhaustion confirm within M bars
        lo_run = l[i]
        hi_run = h[i]
        filled = False
        j_end = min(i + M, n - 1)
        for j in range(i + 1, j_end + 1):
            lo_run = min(lo_run, l[j])
            hi_run = max(hi_run, h[j])
            confirm = (rng[j] < r_i * shrink) or (is_green[j] if cap_down else is_red[j])
            if confirm:
                if cap_down:
                    entry = c[j]
                    sl = lo_run - buf * a
                    sl_d = entry - sl
                    if sl_d > 0:
                        rows.append((t[j], entry, "LONG", sl, entry + tp_r_mult * sl_d, sl_d))
                else:
                    entry = c[j]
                    sl = hi_run + buf * a
                    sl_d = sl - entry
                    if sl_d > 0:
                        rows.append((t[j], entry, "SHORT", sl, entry - tp_r_mult * sl_d, sl_d))
                filled = True
                i = j + 1
                break
        if not filled:
            i = j_end + 1  # invalidated: no confirm within M bars

    sig = pd.DataFrame(rows, columns=["time_utc", "close", "action", "sl_price", "tp_price", "sl_distance"])
    if sig.empty:
        return pd.DataFrame(columns=["time_utc", "close", "action", "sl_price", "tp_price", "sl_distance"])
    return sig
