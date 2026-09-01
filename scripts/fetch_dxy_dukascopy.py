"""Fetch long-history DXY (Dollar Index) from Dukascopy for gold R5 (DXY filter).

Same source/provider as XAUUSD (Dukascopy), so timestamps and session
conventions line up for feature joins. Ticker is DOLLAR.IDX/USD (bid feed).

Usage:
    python scripts/fetch_dxy_dukascopy.py 15m
    python scripts/fetch_dxy_dukascopy.py 1h
    python scripts/fetch_dxy_dukascopy.py 1m     # slow (~1-2h for full range)
"""
import sys
import time
import datetime as dt
from pathlib import Path

import pandas as pd
import dukascopy_python as dk
from dukascopy_python.instruments import INSTRUMENT_IDX_AMERICA_DOLLAR_IDX_USD as DXY

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
START = dt.datetime(2006, 1, 1)

INTERVALS = {
    "1m": (dk.INTERVAL_MIN_1, pd.Timedelta(minutes=1)),
    "15m": (dk.INTERVAL_MIN_15, pd.Timedelta(minutes=15)),
    "1h": (dk.INTERVAL_HOUR_1, pd.Timedelta(hours=1)),
}


def fetch(timeframe: str):
    if timeframe not in INTERVALS:
        raise SystemExit(f"unknown timeframe {timeframe!r}; use one of {list(INTERVALS)}")
    interval, step = INTERVALS[timeframe]
    end = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    print(f"Fetching DXY {timeframe} from {START} to {end} (Dukascopy BID)...")
    t0 = time.time()
    df = dk.fetch(DXY, interval, dk.OFFER_SIDE_BID, START, end)
    print(f"  fetched {len(df)} rows in {time.time()-t0:.1f}s")

    df = df.reset_index().rename(columns={"timestamp": "time_utc"})
    df = df[["time_utc", "open", "high", "low", "close", "volume"]]
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").drop_duplicates("time_utc").reset_index(drop=True)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"DXY_{timeframe}.parquet"
    df.to_parquet(out, index=False)
    print(f"  wrote {len(df)} rows -> {out}")
    print(f"  range: {df['time_utc'].min()} -> {df['time_utc'].max()}")

    gaps = df["time_utc"].diff()
    big = gaps[gaps > step * 1.5]
    weekend_like = big[big > pd.Timedelta(hours=24)]
    print(f"  gaps > 1.5x step: {len(big)}  (of which >24h/weekend-like: {len(weekend_like)})")


if __name__ == "__main__":
    tf = sys.argv[1] if len(sys.argv) > 1 else "1h"
    fetch(tf)
