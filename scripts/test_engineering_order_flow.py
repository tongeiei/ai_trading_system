"""§16 Phase A engineering test #1: place a real (demo) order with SL, verify
the SL sits as a server-side reduce-only STOP_MARKET order — not something
our process has to remember. Then clean up.
"""
import os
import time

import ccxt
from dotenv import load_dotenv

from src.live.order_executor import place_entry_with_sl, cancel_all_and_flatten, fetch_open_algo_orders

load_dotenv()

SYMBOL = "ETH/USDT:USDT"

exchange = ccxt.binanceusdm({
    "apiKey": os.getenv("BINANCE_TESTNET_API_KEY"),
    "secret": os.getenv("BINANCE_TESTNET_API_SECRET"),
    "enableRateLimit": True,
})
exchange.enable_demo_trading(True)
markets = exchange.load_markets()
spec = markets[SYMBOL]

# clean slate first
print("Cleaning up any pre-existing orders/positions...")
cancel_all_and_flatten(exchange, SYMBOL)
time.sleep(1)

ticker = exchange.fetch_ticker(SYMBOL)
mark_price = ticker["last"]
print(f"Mark price: {mark_price}")

qty = spec["limits"]["amount"]["min"]
# make sure min notional is satisfied
min_notional = spec["limits"]["cost"]["min"]
while qty * mark_price < min_notional:
    qty += spec["precision"]["amount"]
qty = round(qty, 4)

sl_price = round(mark_price * 0.97, 1)  # 3% below, well outside noise for a test
print(f"Placing LONG {qty} {SYMBOL} with SL at {sl_price}...")

result = place_entry_with_sl(exchange, SYMBOL, "LONG", qty, sl_price)
print(f"Entry order id: {result['entry_order']['id']}, status: {result['entry_order']['status']}")
print(f"SL order id: {result['sl_order']['id']}, status: {result['sl_order']['status']}")

time.sleep(1)

print("\n--- Verifying SL sits server-side ---")
open_orders = exchange.fetch_open_orders(SYMBOL)
print(f"Regular open orders (fetch_open_orders): {len(open_orders)}")

algo_orders = fetch_open_algo_orders(exchange, SYMBOL)
print(f"Algo/conditional open orders (fapiPrivateGetOpenAlgoOrders): {len(algo_orders)}")
for a in algo_orders:
    print(f"  algoId={a['algoId']} type={a['orderType']} side={a['side']} triggerPrice={a['triggerPrice']} status={a['algoStatus']} reduceOnly={a['reduceOnly']}")

assert len(algo_orders) >= 1, "SL order not found via algo-order endpoint either — it would NOT survive a process crash!"
print("\nPASS: SL order confirmed sitting on exchange as a conditional algo order (server-side, survives process death).")

positions = exchange.fetch_positions([SYMBOL])
open_pos = [p for p in positions if (p.get("contracts") or 0) != 0]
print(f"\nOpen positions: {len(open_pos)}")
for p in open_pos:
    print(f"  side={p['side']} contracts={p['contracts']} entryPrice={p['entryPrice']}")

print("\n--- Cleanup ---")
cancel_all_and_flatten(exchange, SYMBOL)
time.sleep(1)
final_orders = exchange.fetch_open_orders(SYMBOL)
final_algo_orders = [a for a in fetch_open_algo_orders(exchange, SYMBOL) if a["algoStatus"] == "NEW"]
final_positions = [p for p in exchange.fetch_positions([SYMBOL]) if (p.get("contracts") or 0) != 0]
print(f"Remaining open orders: {len(final_orders)} | remaining algo orders: {len(final_algo_orders)} | remaining positions: {len(final_positions)}")
assert len(final_orders) == 0 and len(final_algo_orders) == 0 and len(final_positions) == 0, "Cleanup failed — orphan order/position left on exchange!"
print("PASS: clean flatten confirmed.")
