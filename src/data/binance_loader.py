"""P0: fetch historical OHLCV klines from Binance and store as parquet.

Public market data endpoint — no API key needed, so this pulls from
mainnet (fapiPublic) to get real trading history, not the demo account
which only has a few weeks of synthetic data.
"""
import time
from pathlib import Path

import ccxt
import pandas as pd

RAW_DIR = Path("data/raw")
MS_PER_CANDLE = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000}


def fetch_ohlcv_history(exchange: ccxt.Exchange, symbol: str, timeframe: str, since_ms: int, until_ms: int) -> pd.DataFrame:
    all_rows = []
    cursor = since_ms
    limit = 1500  # binance max per request
    step_ms = MS_PER_CANDLE[timeframe] * limit

    while cursor < until_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit)
        if not batch:
            break
        all_rows.extend(batch)
        last_ts = batch[-1][0]
        if last_ts <= cursor:  # safety against infinite loop
            break
        cursor = last_ts + MS_PER_CANDLE[timeframe]
        exchange.sleep(exchange.rateLimit)

    df = pd.DataFrame(all_rows, columns=["ts_ms", "open", "high", "low", "close", "volume"])
    df["time_utc"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    df = df.drop(columns=["ts_ms"]).drop_duplicates(subset="time_utc").sort_values("time_utc")
    return df.reset_index(drop=True)


def main(symbol: str = "BTC/USDT", timeframe: str = "15m", years: int = 3):
    exchange = ccxt.binanceusdm({"enableRateLimit": True})
    exchange.load_markets()

    until_ms = exchange.milliseconds()
    since_ms = until_ms - int(years * 365 * 24 * 3_600_000)

    print(f"Fetching {symbol} {timeframe} from {pd.to_datetime(since_ms, unit='ms')} to now...")
    df = fetch_ohlcv_history(exchange, symbol, timeframe, since_ms, until_ms)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{symbol.replace('/', '')}_{timeframe}.parquet"
    df.to_parquet(out_path, index=False)

    print(f"Wrote {len(df)} rows to {out_path}")
    print(f"Range: {df['time_utc'].min()} -> {df['time_utc'].max()}")

    gaps = df["time_utc"].diff().dropna()
    expected = pd.Timedelta(minutes=15 if timeframe == "15m" else (1 if timeframe == "1m" else 60))
    n_gaps = (gaps > expected * 1.5).sum()
    print(f"Gaps larger than expected interval: {n_gaps}")


if __name__ == "__main__":
    main()
