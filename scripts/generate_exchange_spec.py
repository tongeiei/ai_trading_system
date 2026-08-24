"""P0: dump BTC/USDT perpetual spec from Binance into config/exchange_spec.yaml.

Re-run whenever the symbol/broker spec might have changed — never hardcode
these values elsewhere in the codebase, always read from this file.
"""
import os

import ccxt
import yaml
from dotenv import load_dotenv

load_dotenv()

SYMBOL = "BTC/USDT:USDT"

exchange = ccxt.binanceusdm({
    "apiKey": os.getenv("BINANCE_TESTNET_API_KEY"),
    "secret": os.getenv("BINANCE_TESTNET_API_SECRET"),
    "enableRateLimit": True,
})
exchange.enable_demo_trading(True)

markets = exchange.load_markets()
m = markets[SYMBOL]

spec = {
    "exchange": "binanceusdm",
    "environment": "demo",  # switch to "mainnet" when promoted — never edit values by hand
    "symbol": SYMBOL,
    "contract_type": "perpetual",
    "quote_currency": m["quote"],
    "precision": {
        "amount_step": m["precision"]["amount"],   # stepSize
        "price_tick": m["precision"]["price"],     # tickSize
    },
    "limits": {
        "amount_min": m["limits"]["amount"]["min"],
        "amount_max": m["limits"]["amount"]["max"],
        "min_notional": m["limits"]["cost"]["min"],
        "price_min": m["limits"]["price"]["min"],
        "price_max": m["limits"]["price"]["max"],
    },
    "maker_fee": m.get("maker"),
    "taker_fee": m.get("taker"),
    "contract_size": m.get("contractSize", 1),
}

os.makedirs("config", exist_ok=True)
with open("config/exchange_spec.yaml", "w") as f:
    yaml.safe_dump(spec, f, sort_keys=False, allow_unicode=True)

print("Wrote config/exchange_spec.yaml")
print(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
