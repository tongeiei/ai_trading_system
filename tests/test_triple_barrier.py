import pandas as pd

from src.labeling.triple_barrier import MAX_HOLD_BARS_M1, label_all_signals


def make_m1_path(entry_time, n_bars, price_fn):
    """n_bars of flat M1 candles starting 1 minute after entry_time, price
    set per-bar by price_fn(i) for OHLC (i is 1-indexed minute offset)."""
    rows = []
    for i in range(1, n_bars + 1):
        t = entry_time + pd.Timedelta(minutes=i)
        p = price_fn(i)
        rows.append({"time_utc": t, "open": p, "high": p, "low": p, "close": p})
    return pd.DataFrame(rows)


def make_signal(entry_time, action, close, sl_price, tp_price):
    return pd.DataFrame([{
        "time_utc": entry_time, "action": action, "close": close,
        "sl_price": sl_price, "tp_price": tp_price,
    }])


def test_default_max_hold_bars_still_12h():
    # regression: the default must stay the live-config value unless deliberately changed
    assert MAX_HOLD_BARS_M1 == 12 * 60


def test_trade_resolves_as_timeout_when_tp_touched_after_default_window():
    entry_time = pd.Timestamp("2025-01-01T00:00:00Z")
    tp_touch_bar = MAX_HOLD_BARS_M1 + 30  # 30 minutes past the 12h default window
    signals = make_signal(entry_time, "LONG", close=100.0, sl_price=95.0, tp_price=110.0)

    def price_fn(i):
        # flat at entry until tp_touch_bar, then jumps to TP
        return 110.0 if i >= tp_touch_bar else 100.0

    m1 = make_m1_path(entry_time, tp_touch_bar + 10, price_fn)

    labeled = label_all_signals(signals, m1)
    assert labeled.iloc[0]["exit_reason"] == "TIMEOUT"


def test_max_hold_bars_parameter_lets_the_same_trade_reach_tp():
    entry_time = pd.Timestamp("2025-01-01T00:00:00Z")
    tp_touch_bar = MAX_HOLD_BARS_M1 + 30  # same setup as above — only the window changes
    signals = make_signal(entry_time, "LONG", close=100.0, sl_price=95.0, tp_price=110.0)

    def price_fn(i):
        return 110.0 if i >= tp_touch_bar else 100.0

    m1 = make_m1_path(entry_time, tp_touch_bar + 10, price_fn)

    extended_hold = MAX_HOLD_BARS_M1 + 60  # 13h — covers the late TP touch
    labeled = label_all_signals(signals, m1, max_hold_bars=extended_hold)
    assert labeled.iloc[0]["exit_reason"] == "TP"
    assert labeled.iloc[0]["r_multiple"] == 2.0  # (110-100)/(100-95)


def test_default_omitted_matches_default_explicit():
    entry_time = pd.Timestamp("2025-01-01T00:00:00Z")
    signals = make_signal(entry_time, "LONG", close=100.0, sl_price=95.0, tp_price=110.0)
    m1 = make_m1_path(entry_time, MAX_HOLD_BARS_M1 + 5, lambda i: 100.0)

    implicit = label_all_signals(signals, m1)
    explicit = label_all_signals(signals, m1, max_hold_bars=MAX_HOLD_BARS_M1)
    assert implicit.iloc[0]["exit_reason"] == explicit.iloc[0]["exit_reason"] == "TIMEOUT"
    assert implicit.iloc[0]["exit_time"] == explicit.iloc[0]["exit_time"]
