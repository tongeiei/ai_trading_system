"""Fetch BTC/USDT SPOT daily klines from Binance (ccxt) — for perp-spot basis
research (docs/research/BTC_EDGE_SEARCH.md Round 6). The existing
data/raw/BTCUSDT_*.parquet files are USDⓈ-M PERPETUAL futures (they carry
a funding rate); this fetches the spot leg so basis = perp - spot can be
computed.

Usage:
    python scripts/fetch_btc_spot_binance.py
"""
import time
from pathlib import Path

import ccxt
import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
SYMBOL = "BTC/USDT"
TIMEFRAME = "1d"
START_MS = ccxt.binance().parse8601("2019-01-01T00:00:00Z")


def fetch():
    ex = ccxt.binance({"enableRateLimit": True})
    all_rows = []
    since = START_MS
    while True:
        batch = ex.fetch_ohlcv(SYMBOL, TIMEFRAME, since=since, limit=1000)
        if not batch:
            break
        all_rows.extend(batch)
        last_ts = batch[-1][0]
        if last_ts <= since:
            break
        since = last_ts + 1
        if len(batch) < 1000:
            break
        time.sleep(ex.rateLimit / 1000)

    df = pd.DataFrame(all_rows, columns=["time_utc", "open", "high", "low", "close", "volume"])
    df["time_utc"] = pd.to_datetime(df["time_utc"], unit="ms", utc=True)
    df = df.sort_values("time_utc").drop_duplicates("time_utc").reset_index(drop=True)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "BTCUSDT_SPOT_daily.parquet"
    df.to_parquet(out, index=False)
    print(f"wrote {len(df)} rows -> {out}")
    print(f"range: {df['time_utc'].min()} -> {df['time_utc'].max()}")


if __name__ == "__main__":
    fetch()
