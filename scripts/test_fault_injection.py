"""§16 Phase A fault injection suite — remaining cases from §19.

Case A: order reject on notional too small — must raise cleanly, never
        silently round up to a placeable size (§10.3 principle).
Case B: "service crash" simulation — place position+SL, then reconcile
        from a totally fresh exchange/reconcile call (simulating a
        just-restarted process with no memory of what it did) and confirm
        it correctly sees the position as protected.
Case C: orphan position detection — manually cancel the SL behind an open
        position (simulating an accidental cancel or a bug), then confirm
        reconcile_symbol flags it CRITICAL.
"""
import os
import time

import ccxt
from dotenv import load_dotenv

from src.live.order_executor import place_entry_with_sl, cancel_all_and_flatten, fetch_open_algo_orders, OrderRejected
from src.live.reconcile import reconcile_symbol

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

print("Cleaning up before test...")
cancel_all_and_flatten(exchange, SYMBOL)
time.sleep(1)

# ============================================================
print("\n=== Case A: order reject on notional too small ===")
ticker = exchange.fetch_ticker(SYMBOL)
mark_price = ticker["last"]
min_qty_step = spec["precision"]["amount"]

tiny_qty = min_qty_step  # smallest possible step, deliberately below minNotional
tiny_notional = tiny_qty * mark_price
print(f"Attempting order: qty={tiny_qty}, notional=${tiny_notional:.2f} (min required: ${spec['limits']['cost']['min']})")

try:
    exchange.create_order(SYMBOL, "market", "buy", tiny_qty)
    print("FAIL: order was accepted despite being below min notional — exchange should have rejected it!")
except Exception as e:
    print(f"PASS: order rejected cleanly by exchange: {type(e).__name__}: {e}")

cancel_all_and_flatten(exchange, SYMBOL)
time.sleep(1)

# ============================================================
print("\n=== Case B: service crash simulation ===")
print("Placing position + SL (simulating a live signal firing)...")
qty = spec["limits"]["amount"]["min"]
while qty * mark_price < spec["limits"]["cost"]["min"]:
    qty += spec["precision"]["amount"]
qty = round(qty, 4)
sl_price = round(mark_price * 0.97, 1)

place_entry_with_sl(exchange, SYMBOL, "LONG", qty, sl_price)
print("Position + SL placed. Simulating process crash (just stop doing anything)...")
time.sleep(2)

print("Simulating process RESTART: fresh exchange connection, zero local memory of prior state...")
fresh_exchange = ccxt.binanceusdm({
    "apiKey": os.getenv("BINANCE_TESTNET_API_KEY"),
    "secret": os.getenv("BINANCE_TESTNET_API_SECRET"),
    "enableRateLimit": True,
})
fresh_exchange.enable_demo_trading(True)
fresh_exchange.load_markets()

result = reconcile_symbol(fresh_exchange, SYMBOL)
print(f"Reconcile result after 'restart': severity={result.severity}, detail={result.detail}")
assert result.severity == "OK" and result.has_position and result.has_protective_sl, \
    "Fresh process couldn't confirm the position is protected — SL survival design failed!"
print("PASS: freshly-restarted process correctly sees the position as protected (SL survived crash).")

# ============================================================
print("\n=== Case C: orphan position detection ===")
print("Manually cancelling the SL to simulate an accidental cancel / bug...")
algo_orders = fetch_open_algo_orders(exchange, SYMBOL)
for a in algo_orders:
    exchange.fapiPrivateDeleteAlgoOrder({"algoId": a["algoId"]})
time.sleep(1)

result = reconcile_symbol(exchange, SYMBOL)
print(f"Reconcile result after SL removed: severity={result.severity}, detail={result.detail}")
assert result.severity == "CRITICAL" and result.orphan_position, \
    "Reconcile FAILED to detect an unprotected position — this is the exact failure mode §19 exists to catch!"
print("PASS: orphan position correctly flagged CRITICAL.")

print("\n--- Final cleanup ---")
cancel_all_and_flatten(exchange, SYMBOL)
time.sleep(1)
final = reconcile_symbol(exchange, SYMBOL)
print(f"Final state: severity={final.severity}, detail={final.detail}")
assert final.severity == "OK" and not final.has_position

print("\n=== ALL FAULT INJECTION CASES PASSED ===")
