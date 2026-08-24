"""Triple-barrier labeling per PROJECT_PLAN.md §4.3 (López de Prado).

Uses M1 path data to resolve which barrier (TP/SL) is touched first —
M15 OHLC alone can't tell you whether the high or the low came first within
a bar, and guessing wrong systematically flatters the backtest (§14.1).
"""
import numpy as np
import pandas as pd

MAX_HOLD_BARS_M1 = 12 * 60  # 12 hours, per §4.3


def label_signal(
    entry_time: pd.Timestamp,
    action: str,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    m1_path: pd.DataFrame,
) -> dict:
    """m1_path must be pre-sliced to bars strictly after entry_time, sorted ascending.
    Returns dict with label (1=TP hit first, 0=SL hit first or timeout-negative),
    exit_time, exit_price, exit_reason, r_multiple.
    """
    window = m1_path[m1_path["time_utc"] > entry_time].head(MAX_HOLD_BARS_M1)
    if window.empty:
        return {"label": None, "exit_reason": "no_data", "exit_time": None, "exit_price": None, "r_multiple": None}

    sl_distance = abs(entry_price - sl_price)

    for _, bar in window.iterrows():
        if action == "LONG":
            hit_sl = bar["low"] <= sl_price
            hit_tp = bar["high"] >= tp_price
        else:  # SHORT
            hit_sl = bar["high"] >= sl_price
            hit_tp = bar["low"] <= tp_price

        if hit_sl and hit_tp:
            # both touched in same M1 bar — conservative assumption: SL hit first
            return _result(0, bar["time_utc"], sl_price, "SL_TP_same_bar_conservative", sl_price, entry_price, action, sl_distance)
        if hit_sl:
            return _result(0, bar["time_utc"], sl_price, "SL", sl_price, entry_price, action, sl_distance)
        if hit_tp:
            return _result(1, bar["time_utc"], tp_price, "TP", tp_price, entry_price, action, sl_distance)

    # timeout: close at last available price, label by sign of R
    last_bar = window.iloc[-1]
    exit_price = last_bar["close"]
    r = _r_multiple(entry_price, exit_price, sl_distance, action)
    return _result(1 if r > 0 else 0, last_bar["time_utc"], exit_price, "TIMEOUT", exit_price, entry_price, action, sl_distance)


def _r_multiple(entry_price, exit_price, sl_distance, action):
    diff = (exit_price - entry_price) if action == "LONG" else (entry_price - exit_price)
    return diff / sl_distance


def _result(label, exit_time, exit_price_barrier, exit_reason, exit_price, entry_price, action, sl_distance):
    r = _r_multiple(entry_price, exit_price_barrier, sl_distance, action)
    return {
        "label": label,
        "exit_time": exit_time,
        "exit_price": exit_price_barrier,
        "exit_reason": exit_reason,
        "r_multiple": r,
    }


def label_all_signals(signals: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    """signals: output of generate_v0_signals filtered to action != NO_TRADE.
    m1: full M1 OHLC history, sorted by time_utc.

    Uses binary search (np.searchsorted) to slice each signal's forward
    window instead of re-scanning the full M1 frame per signal — with 1.5M+
    M1 rows and thousands of signals, a boolean-mask-per-row approach is
    O(n_signals * n_m1) and becomes impractically slow.
    """
    m1 = m1.sort_values("time_utc").reset_index(drop=True)
    m1_times = m1["time_utc"]  # keep as tz-aware pandas Series; DatetimeIndex.searchsorted handles tz correctly

    results = []
    for _, sig in signals.iterrows():
        entry_time = sig["time_utc"]
        start_idx = m1_times.searchsorted(entry_time, side="right")
        end_idx = min(start_idx + MAX_HOLD_BARS_M1, len(m1))
        window = m1.iloc[start_idx:end_idx]

        res = _label_from_window(
            action=sig["action"],
            entry_price=sig["close"],
            sl_price=sig["sl_price"],
            tp_price=sig["tp_price"],
            window=window,
        )
        results.append({**sig.to_dict(), **res})
    return pd.DataFrame(results)


def _label_from_window(action: str, entry_price: float, sl_price: float, tp_price: float, window: pd.DataFrame) -> dict:
    if window.empty:
        return {"label": None, "exit_reason": "no_data", "exit_time": None, "exit_price": None, "r_multiple": None}

    sl_distance = abs(entry_price - sl_price)

    for _, bar in window.iterrows():
        if action == "LONG":
            hit_sl = bar["low"] <= sl_price
            hit_tp = bar["high"] >= tp_price
        else:
            hit_sl = bar["high"] >= sl_price
            hit_tp = bar["low"] <= tp_price

        if hit_sl and hit_tp:
            return _result(0, bar["time_utc"], sl_price, "SL_TP_same_bar_conservative", sl_price, entry_price, action, sl_distance)
        if hit_sl:
            return _result(0, bar["time_utc"], sl_price, "SL", sl_price, entry_price, action, sl_distance)
        if hit_tp:
            return _result(1, bar["time_utc"], tp_price, "TP", tp_price, entry_price, action, sl_distance)

    last_bar = window.iloc[-1]
    exit_price = last_bar["close"]
    r = _r_multiple(entry_price, exit_price, sl_distance, action)
    return _result(1 if r > 0 else 0, last_bar["time_utc"], exit_price, "TIMEOUT", exit_price, entry_price, action, sl_distance)
