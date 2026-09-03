"""MT5 live-feed SPIKE for XAU/USD — P2 (docs/XAU_ARCHITECTURE_AUDIT.md §10).

This is a feasibility prototype, not a production live loop: it proves bars
can be pulled from MT5 and pass the validation layer (src/data/validation.py).
It does NOT do retry/reconnect, scheduling, persistence into src/data/db.py's
`bars` table, or wiring into a pluggable data-source interface — all of that
is later-phase (P8 execution / live monitor loop) territory, deliberately out
of scope here.

Windows-only (MetaTrader5 package). Symbol is `XAUUSDm` (Exness suffix,
confirmed in docs/XAU_LIVE_HANDOFF.md) — this module is Exness-specific by
design for the spike; a broker-agnostic symbol lookup is future work.
"""
from __future__ import annotations

import MetaTrader5 as mt5
import pandas as pd

from src.data.validation import ValidationReport, validate_timeframe

SYMBOL = "XAUUSDm"

MT5_TIMEFRAMES = {
    "m1": mt5.TIMEFRAME_M1,
    "m5": mt5.TIMEFRAME_M5,
    "m15": mt5.TIMEFRAME_M15,
    "h1": mt5.TIMEFRAME_H1,
    "h4": mt5.TIMEFRAME_H4,
}

# Matches validate_timeframe's TIMEFRAME_STEPS naming ("1m"/"5m"/"15m"/"1h"/"4h").
VALIDATION_TIMEFRAME = {"m1": "1m", "m5": "5m", "m15": "15m", "h1": "1h", "h4": "4h"}


def connect() -> bool:
    """Wraps mt5.initialize(). Returns False (never raises) on failure so
    callers can fail safe — see module docstring."""
    return bool(mt5.initialize())


def disconnect() -> None:
    mt5.shutdown()


def fetch_recent_bars(timeframe_key: str, n_bars: int = 500) -> pd.DataFrame:
    """Pulls the last n_bars closed bars for SYMBOL at the given timeframe key
    (one of MT5_TIMEFRAMES). Drops the still-forming current bar the same way
    src/live/signal_service.py:fetch_recent_ohlcv drops an unclosed exchange
    candle — position 0 in MT5's copy_rates_from_pos is the CURRENT
    (still-forming) bar, so we fetch n_bars+1 starting at position 1 to get
    n_bars fully-closed bars.
    """
    mt5_tf = MT5_TIMEFRAMES[timeframe_key]
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5_tf, 1, n_bars)
    if rates is None or len(rates) == 0:
        return pd.DataFrame(columns=["time_utc", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(rates)
    df["time_utc"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(columns={"tick_volume": "volume"})
    df = df[["time_utc", "open", "high", "low", "close", "volume"]]
    return df.sort_values("time_utc").drop_duplicates(subset="time_utc").reset_index(drop=True)


def spike_check(n_bars: int = 500) -> dict[str, ValidationReport]:
    """Connects, fetches all 5 timeframes for SYMBOL, validates each,
    disconnects. Returns {timeframe_key: ValidationReport}. This is the
    deliverable the P2 DoD's 'live-feed spike' refers to — a feasibility
    check, not a running service.
    """
    if not connect():
        raise RuntimeError(f"mt5.initialize() failed: {mt5.last_error()}")

    try:
        reports: dict[str, ValidationReport] = {}
        for tf_key in MT5_TIMEFRAMES:
            df = fetch_recent_bars(tf_key, n_bars=n_bars)
            reports[tf_key] = validate_timeframe(df, VALIDATION_TIMEFRAME[tf_key])
        return reports
    finally:
        disconnect()


if __name__ == "__main__":
    results = spike_check()
    all_ok = True
    for tf_key, report in results.items():
        print(report.summary())
        for issue in report.issues:
            if issue.severity == "error":
                print(f"  ERROR [{issue.kind}] {issue.time_utc}: {issue.detail}")
        all_ok = all_ok and report.ok
    print("\nSPIKE " + ("OK" if all_ok else "FAILED"))
