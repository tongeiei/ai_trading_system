"""P0 sanity check: authenticate against Binance USDⓈ-M Futures demo/testnet via ccxt.

Verifies:
  1. auth works (fetch balance)
  2. load_markets() works and returns BTC/USDT spec
"""
import os

import ccxt
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("BINANCE_TESTNET_API_KEY")
api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")

if not api_key or not api_secret:
    raise SystemExit("Missing BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_API_SECRET in .env")

exchange = ccxt.binanceusdm({
    "apiKey": api_key,
    "secret": api_secret,
    "enableRateLimit": True,
})

# ccxt dropped classic testnet/sandbox mode for futures; Binance's replacement is
# "demo trading" (demo-fapi.binance.com), which ccxt exposes via enable_demo_trading().
exchange.enable_demo_trading(True)

print("Using API base:", exchange.urls["api"]["fapiPrivate"])

print("\n--- fetch_balance() ---")
balance = exchange.fetch_balance()
usdt = balance.get("USDT", {})
print("USDT total:", usdt.get("total"), "| free:", usdt.get("free"))

print("\n--- load_markets() ---")
markets = exchange.load_markets()
btc = markets.get("BTC/USDT:USDT")  # ccxt unified symbol for the USDT-margined perpetual
if btc:
    print("BTC/USDT precision:", btc["precision"])
    print("BTC/USDT limits:", btc["limits"])
else:
    print("BTC/USDT market not found — check symbol naming for this exchange instance")

print("\nOK — connection + auth working.")
