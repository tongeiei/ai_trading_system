"""Fetch data for the pre-registered 2nd-symbol candidate shortlist.

Shortlist (fixed BEFORE looking at any backtest result, to limit the
multiple-comparison problem): the 6 most-liquid, long-established Binance
USDⓈ-M perps not already tested — XRP, DOGE, ADA, LINK, LTC, AVAX. All
listed 2020 or earlier (>=3yr history, comparable to the ETH/BTC tests).

Same 3-year window and locked-config discipline as fetch_multi_symbol.py.
"""
from src.data.binance_loader import main as fetch_klines
from src.data.funding_rate_loader import main as fetch_funding

SYMBOLS = ["XRP/USDT", "DOGE/USDT", "ADA/USDT", "LINK/USDT", "LTC/USDT", "AVAX/USDT"]

for sym in SYMBOLS:
    print(f"\n=== {sym} ===")
    fetch_klines(symbol=sym, timeframe="15m", years=3)
    fetch_klines(symbol=sym, timeframe="1h", years=3)
    fetch_klines(symbol=sym, timeframe="1m", years=3)
    fetch_funding(symbol=f"{sym}:USDT", years=3)

print("\nAll candidate symbols fetched.")
