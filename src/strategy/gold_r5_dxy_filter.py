"""R5 — DXY regime filter for XAU/USD spot.

Hypothesis (docs/research/XAU_REDDIT_SCOUT.md, R5):
    "เข้า long gold เฉพาะเมื่อ DXY อยู่ต่ำกว่า MA (USD อ่อน) และกลับกัน"
    i.e. gold and the US dollar index have a real fundamental relationship
    (gold is priced in USD; a weakening dollar mechanically makes gold
    relatively cheaper for other-currency buyers, and both often respond to
    the same macro driver — real-rate expectations / risk sentiment).

Mechanism ("who pays you"): this is NOT a momentum/pattern edge on gold's own
tape (those are the ones R1/R2/R8/R11/R14 already falsified). It's a claim
that a slow-moving macro REGIME (USD strength vs its own trailing average)
has directional information for gold that a same-instrument-only signal
cannot see — participants trading gold on technicals alone are "fighting"
the macro tide when regime and trade direction disagree.

Rule (if/then), evaluated once per UTC calendar day at a fixed session time
(08:00 UTC, London open — same entry timing used across the R-track so this
test isolates the DXY variable, not entry-timing choice):

    regime_t = sign(DXY_close_asof(t) - DXY_MA_n_asof(t))
        DXY_MA_n = n-bar SMA of DXY DAILY close (n in {20,50,100,200})
        "asof(t)" = the last COMPLETED DXY daily bar as of entry time t,
        using a full extra day of lag beyond the bar's own timestamp for
        safety (DXY_daily bars are stamped ~04:00-05:00 UTC on day D; we
        only consider that bar's close usable starting 00:00 UTC on D+1).
        regime_t = -1  -> USD below its MA ("weak dollar")
        regime_t = +1  -> USD above its MA ("strong dollar")

    direction modes (grid, see runner):
      regime_directional : LONG if regime==-1 else SHORT if regime==+1
      regime_long_filter : LONG if regime==-1 else NO_TRADE   (long-only filter)
      regime_short_filter: SHORT if regime==+1 else NO_TRADE  (short-only filter)
      always_long         : LONG every day, ignores regime      (baseline)
      always_short         : SHORT every day, ignores regime     (baseline)
      inverted_directional: LONG if regime==+1 else SHORT if regime==-1
                             (contrarian sanity-check: does the OPPOSITE
                             regime mapping also "work"? if so, the whole
                             thing is noise, not a real macro relationship)

    entry:      first m15 bar with hour==entry_hour (08:00 UTC London open),
                entry price = that bar's OPEN (known/executable at bar start,
                not its close, to avoid using information from within the bar)
    sl_price:   entry -/+ k_sl * ATR14(m15) as of the PRIOR bar's close
                (no look-ahead: ATR window uses only bars strictly before entry)
    tp_price:   entry +/- tp_r_mult * sl_distance
    fixed (not swept): entry_hour=8, k_sl=1.5, tp_r_mult=2.0, atr_len=14 —
    kept fixed so the sweep isolates the DXY-regime variable itself, not
    entry-mechanics tuning (which would reopen the R1/R2 in-sample-selection
    problem for a variable this test isn't trying to validate).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def load_dxy_regime(dxy: pd.DataFrame, ma_len: int) -> pd.DataFrame:
    """Daily DXY -> regime series with an explicit "available_time" that is
    always >= 1 full UTC day after the bar's own timestamp, so joining onto
    intraday XAU bars can never see a same-day-or-later, not-yet-closed DXY
    value (see module docstring for the look-ahead rationale)."""
    d = dxy[["time_utc", "close"]].copy()
    d["time_utc"] = pd.to_datetime(d["time_utc"], utc=True).astype("datetime64[us, UTC]")
    d = d.sort_values("time_utc").reset_index(drop=True)
    d["ma"] = d["close"].rolling(ma_len, min_periods=ma_len).mean()
    d["regime"] = np.sign(d["close"] - d["ma"])
    # usable starting the NEXT UTC calendar day at 00:00 (>= 1 full day lag)
    d["available_time"] = d["time_utc"].dt.normalize() + pd.Timedelta(days=1)
    return d[["available_time", "regime"]].dropna().sort_values("available_time").reset_index(drop=True)


def generate_r5_signals(
    m15: pd.DataFrame,
    dxy: pd.DataFrame,
    ma_len: int = 50,
    mode: str = "regime_directional",
    entry_hour: int = 8,
    k_sl: float = 1.5,
    tp_r_mult: float = 2.0,
    atr_len: int = 14,
) -> pd.DataFrame:
    df = m15[["time_utc", "open", "high", "low", "close"]].copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)
    df["atr"] = _atr(df, atr_len).shift(1)  # as-of PRIOR bar close, no look-ahead
    df["date"] = df["time_utc"].dt.date
    df["hour"] = df["time_utc"].dt.hour
    df["minute"] = df["time_utc"].dt.minute

    # first bar at/after entry_hour:00 each day
    cand = df[(df["hour"] == entry_hour) & (df["minute"] == 0)].copy()
    if cand.empty:
        cand = df[df["hour"] == entry_hour].groupby("date", as_index=False).first()
    cand = cand.drop_duplicates(subset="date", keep="first").reset_index(drop=True)

    regime_tbl = load_dxy_regime(dxy, ma_len)
    cand = cand.sort_values("time_utc")
    cand["time_utc"] = cand["time_utc"].astype("datetime64[us, UTC]")
    cand = pd.merge_asof(
        cand, regime_tbl, left_on="time_utc", right_on="available_time", direction="backward"
    )

    entry = cand["open"]
    atr = cand["atr"]
    regime = cand["regime"]

    action = pd.Series("NO_TRADE", index=cand.index, dtype=object)
    if mode == "regime_directional":
        action[regime == -1] = "LONG"
        action[regime == 1] = "SHORT"
    elif mode == "regime_long_filter":
        action[regime == -1] = "LONG"
    elif mode == "regime_short_filter":
        action[regime == 1] = "SHORT"
    elif mode == "inverted_directional":
        action[regime == 1] = "LONG"
        action[regime == -1] = "SHORT"
    elif mode == "always_long":
        action[:] = "LONG"
    elif mode == "always_short":
        action[:] = "SHORT"
    else:
        raise ValueError(f"unknown mode: {mode}")

    valid_atr = atr.notna() & (atr > 0)
    action[~valid_atr] = "NO_TRADE"

    sl_price = pd.Series(np.nan, index=cand.index, dtype="float64")
    tp_price = pd.Series(np.nan, index=cand.index, dtype="float64")
    is_long = action == "LONG"
    is_short = action == "SHORT"
    sl_price[is_long] = entry[is_long] - k_sl * atr[is_long]
    sl_price[is_short] = entry[is_short] + k_sl * atr[is_short]
    sl_distance = (entry - sl_price).abs()

    tp_price[is_long] = entry[is_long] + tp_r_mult * sl_distance[is_long]
    tp_price[is_short] = entry[is_short] - tp_r_mult * sl_distance[is_short]

    bad = (action != "NO_TRADE") & ~(sl_distance > 0)
    action[bad] = "NO_TRADE"

    out = pd.DataFrame({
        "time_utc": cand["time_utc"],
        "close": entry,
        "action": action,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "sl_distance": sl_distance,
    })
    return out.reset_index(drop=True)
