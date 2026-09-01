"""R11 — Wick-Fill / Imbalance Revert, XAU/USD spot.

Hypothesis (docs/research/R11_R13_PLAN.md, R11 section, mechanism: momentum
chasers trapped at the tip of an abnormally long wick must cut losses -> price
tends to revert and "fill the wick").

On m15, per closed bar i:
  atr        = ATR(atr_len) as of bar i's OWN close (no shift needed — the ATR
               window uses bars up to and including i, all already closed by
               the time we evaluate the trigger at close_i; entry itself is at
               close_i, not a future bar, so there is no look-ahead)
  lower_wick = min(open_i, close_i) - low_i
  body       = |close_i - open_i|
  trigger LONG (fade the lower wick):
    lower_wick >= k_wick * atr
    AND body <= body_frac * lower_wick        (rejection candle, not a trend candle)
    AND bar i's hour is in the high-liquidity session window
    THEN action=LONG at close_i (close = entry price)
    sl_price    = low_i - buf * atr
    sl_distance = close_i - sl_price (> 0)
    tp_price:
      tp_mode="wick_fill" -> open_i if open_i > close_i else high_i (fallback
        when open is not meaningfully above the entry — see note below)
      tp_mode="1.0R"/"1.5R" -> close_i + tp_r_mult * sl_distance
  SHORT mirrors with upper_wick = high_i - max(open_i, close_i), tp fallback low_i.
  one-trade rule: harness/triple-barrier already enforces "next signal only
  after this trade resolves" is NOT automatic here (unlike R2/R8's per-day/
  per-arm scan) — R11 signals are evaluated independently bar-by-bar, so we
  explicitly suppress new arms while a previous still-open trade would overlap
  by tracking a simple "next allowed bar" pointer (no overlapping arms).
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


def generate_r11_signals(
    m15: pd.DataFrame,
    atr_len: int = 14,
    k_wick: float = 1.5,
    body_frac: float = 0.5,
    buf: float = 0.1,
    tp_mode: str = "wick_fill",   # "wick_fill" | "1.0R" | "1.5R"
    direction: str = "both",       # "both" | "long"
    session_filter: bool = True,
    baseline: bool = False,        # True -> mean-reversion baseline (§6 red flag check):
                                    # same session/SL/TP construction but NO wick/body filter
                                    # (trigger on every closed bar).
) -> pd.DataFrame:
    df = m15[["time_utc", "open", "high", "low", "close"]].copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)

    df["atr"] = _atr(df, atr_len)
    df["hour"] = df["time_utc"].dt.hour

    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    atr = df["atr"].to_numpy()
    hour = df["hour"].to_numpy()
    t = df["time_utc"].to_numpy()

    allow_long = direction in ("both", "long")
    allow_short = direction in ("both",)

    if tp_mode == "wick_fill":
        tp_r_mult = None
    elif tp_mode == "1.0R":
        tp_r_mult = 1.0
    elif tp_mode == "1.5R":
        tp_r_mult = 1.5
    else:
        raise ValueError(f"unknown tp_mode: {tp_mode}")

    n = len(df)
    rows = []
    next_allowed = 0  # bar index at/after which a new arm is allowed (no overlap)

    for i in range(n):
        if i < next_allowed:
            continue
        a = atr[i]
        if not (a > 0) or np.isnan(a):
            continue
        if session_filter and hour[i] not in HIGH_LIQ_HOURS:
            continue

        lower_wick = min(o[i], c[i]) - l[i]
        upper_wick = h[i] - max(o[i], c[i])
        body = abs(c[i] - o[i])

        if baseline:
            # naive mean-reversion baseline (§6 red flag check): NO wick-length
            # / body-shape filter at all — trade every closed bar in the
            # session, direction picked by which side has the bigger wick
            # (so it fires on ~every bar, not just "abnormal" ones), SAME
            # SL/TP construction as the real rule. This isolates whether the
            # k_wick/body_frac threshold itself adds anything over generic
            # every-bar mean reversion.
            is_long = allow_long and (lower_wick >= upper_wick or not allow_short)
            is_short = allow_short and not is_long
        else:
            lower_wick_ok = allow_long and lower_wick >= k_wick * a and body <= body_frac * lower_wick
            upper_wick_ok = allow_short and upper_wick >= k_wick * a and body <= body_frac * upper_wick
            is_long = lower_wick_ok
            is_short = upper_wick_ok and not is_long

        if is_long:
            sl_price = l[i] - buf * a
            sl_d = c[i] - sl_price
            if sl_d > 0:
                if tp_mode == "wick_fill":
                    tp_price = o[i] if o[i] > c[i] else h[i]
                    if not (tp_price > c[i]):
                        tp_price = c[i] + sl_d  # degenerate fallback: 1R
                else:
                    tp_price = c[i] + tp_r_mult * sl_d
                rows.append((t[i], c[i], "LONG", sl_price, tp_price, sl_d))
                next_allowed = i + 1
                continue
        if is_short:
            sl_price = h[i] + buf * a
            sl_d = sl_price - c[i]
            if sl_d > 0:
                if tp_mode == "wick_fill":
                    tp_price = o[i] if o[i] < c[i] else l[i]
                    if not (tp_price < c[i]):
                        tp_price = c[i] - sl_d
                else:
                    tp_price = c[i] - tp_r_mult * sl_d
                rows.append((t[i], c[i], "SHORT", sl_price, tp_price, sl_d))
                next_allowed = i + 1

    cols = ["time_utc", "close", "action", "sl_price", "tp_price", "sl_distance"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)
