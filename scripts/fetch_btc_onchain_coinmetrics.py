"""Fetch free Coin Metrics Community on-chain/network data for BTC.

New data dimension for the BTC edge search — not OHLCV/funding derived, so
it doesn't overlap the 4 pre-registered hypotheses already tested and
rejected (see docs/research/BTC_EDGE_SEARCH.md, docs/FINDINGS.md). No API
key required; Community CSVs are public.

Source: https://github.com/coinmetrics/data (community, free, daily
granularity). Pulls the full btc.csv and keeps a curated subset of
columns that are plausible economic drivers (on-chain activity, exchange
flow proxies, realized-cap based valuation) rather than every column
Coin Metrics publishes.

Usage:
    python scripts/fetch_btc_onchain_coinmetrics.py
"""
import sys
import time
from pathlib import Path

import pandas as pd
import requests

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
CSV_URL = "https://raw.githubusercontent.com/coinmetrics/data/master/csv/btc.csv"

# Curated subset: on-chain activity + valuation metrics plausible as a BTC
# economic driver. Full column list is in the fetched file's header if more
# are wanted later — pick the same columns for the next hypothesis rather
# than re-fetching.
KEEP_COLS = [
    "time",
    "AdrActCnt",       # active addresses
    "TxCnt",           # transaction count
    "TxTfrValMeanUSD", # mean transfer value (USD)
    "FeeMeanUSD",      # mean fee (USD)
    "CapMrktCurUSD",   # market cap (current supply)
    "CapRealUSD",      # realized cap
    "HashRate",        # network hashrate
    "SplyCur",         # current circulating supply
]


def fetch():
    print(f"Fetching {CSV_URL} ...")
    t0 = time.time()
    resp = requests.get(CSV_URL, timeout=120)
    resp.raise_for_status()
    print(f"  downloaded {len(resp.content)/1e6:.1f}MB in {time.time()-t0:.1f}s")

    from io import StringIO
    df = pd.read_csv(StringIO(resp.text), low_memory=False)

    missing = [c for c in KEEP_COLS if c not in df.columns]
    if missing:
        print(f"  WARNING: columns not found in source, dropping from KEEP_COLS: {missing}")
    cols = [c for c in KEEP_COLS if c in df.columns]
    df = df[cols].rename(columns={"time": "time_utc"})
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").drop_duplicates("time_utc").reset_index(drop=True)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "BTC_onchain_coinmetrics_daily.parquet"
    df.to_parquet(out, index=False)
    print(f"  wrote {len(df)} rows x {len(df.columns)} cols -> {out}")
    print(f"  range: {df['time_utc'].min()} -> {df['time_utc'].max()}")
    print(f"  columns: {list(df.columns)}")
    print(f"  non-null coverage:\n{df.notna().mean().round(3)}")


if __name__ == "__main__":
    fetch()
