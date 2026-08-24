"""P0: fetch historical funding rate for BTC/USDT perpetual -> parquet.

Needed as a cost input in backtest EV calc (see PROJECT_PLAN.md §8) —
funding is charged every 8h and ignoring it overstates expected value.
"""
from pathlib import Path

import ccxt
import pandas as pd

RAW_DIR = Path("data/raw")


def main(symbol: str = "BTC/USDT:USDT", years: int = 3):
    exchange = ccxt.binanceusdm({"enableRateLimit": True})
    exchange.load_markets()

    until_ms = exchange.milliseconds()
    since_ms = until_ms - int(years * 365 * 24 * 3_600_000)

    print(f"Fetching funding rate history for {symbol}...")
    all_rows = []
    cursor = since_ms
    while cursor < until_ms:
        batch = exchange.fetch_funding_rate_history(symbol, since=cursor, limit=1000)
        if not batch:
            break
        all_rows.extend(batch)
        last_ts = batch[-1]["timestamp"]
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
        exchange.sleep(exchange.rateLimit)

    df = pd.DataFrame([{
        "time_utc": pd.to_datetime(r["timestamp"], unit="ms", utc=True),
        "funding_rate": r["fundingRate"],
        "symbol": r["symbol"],
    } for r in all_rows]).drop_duplicates(subset="time_utc").sort_values("time_utc")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{symbol.replace('/', '').replace(':', '_')}_funding.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")
    print(f"Range: {df['time_utc'].min()} -> {df['time_utc'].max()}")
    print(f"Mean funding rate: {df['funding_rate'].mean():.6f} ({df['funding_rate'].mean()*3*365*100:.2f}% annualized)")


if __name__ == "__main__":
    main()
