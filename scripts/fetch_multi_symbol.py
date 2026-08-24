"""Fetch M15/H1/M1/funding for ETH, SOL, BNB (BTC already have) — 3 years each,
same locked V0 config (ADX35, SL2.5x) as the BTC holdout test, no re-tuning."""
from src.data.binance_loader import main as fetch_klines
from src.data.funding_rate_loader import main as fetch_funding

SYMBOLS = ["ETH/USDT", "SOL/USDT", "BNB/USDT"]

for sym in SYMBOLS:
    print(f"\n=== {sym} ===")
    fetch_klines(symbol=sym, timeframe="15m", years=3)
    fetch_klines(symbol=sym, timeframe="1h", years=3)
    fetch_klines(symbol=sym, timeframe="1m", years=3)
    fetch_funding(symbol=f"{sym}:USDT", years=3)

print("\nAll symbols fetched.")
