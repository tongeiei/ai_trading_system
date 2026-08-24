"""§16 Phase A: verify DB records match reality after a full execute_signal_with_logging
call on demo trading — including the rejected-signal path (min notional)."""
import os
import time

import ccxt
from dotenv import load_dotenv
from sqlalchemy import select

from src.data.db import init_db, signals, risk_decisions, orders, trades
from src.live.order_executor import execute_signal_with_logging, cancel_all_and_flatten, OrderRejected
from src.risk.sizing import ExchangeSpec

load_dotenv()
SYMBOL = "ETH/USDT:USDT"
DB_PATH = "data/trading_engineering_test.db"

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
engine = init_db(DB_PATH)

exchange = ccxt.binanceusdm({
    "apiKey": os.getenv("BINANCE_TESTNET_API_KEY"),
    "secret": os.getenv("BINANCE_TESTNET_API_SECRET"),
    "enableRateLimit": True,
})
exchange.enable_demo_trading(True)
markets = exchange.load_markets()
spec = markets[SYMBOL]

cancel_all_and_flatten(exchange, SYMBOL)
time.sleep(1)

ticker = exchange.fetch_ticker(SYMBOL)
mark_price = ticker["last"]
exchange_spec = ExchangeSpec(
    amount_step=spec["precision"]["amount"],
    amount_min=spec["limits"]["amount"]["min"],
    min_notional=spec["limits"]["cost"]["min"],
)

print("=== Case 1: rejected signal (risk too tiny -> below min notional) ===")
try:
    execute_signal_with_logging(
        exchange, engine, SYMBOL, "M15", "LONG", "TREND",
        entry_price=mark_price, sl_price=mark_price * 0.999, tp_price=mark_price * 1.002,
        risk_pct=0.000005, equity=1000, exchange_spec=exchange_spec,  # deliberately tiny -> notional < min_notional
    )
    print("FAIL: expected OrderRejected")
except OrderRejected as e:
    print(f"PASS: rejected as expected: {e}")

with engine.connect() as conn:
    rejected_signals = conn.execute(select(signals).where(signals.c.decision == "REJECTED")).fetchall()
print(f"DB shows {len(rejected_signals)} rejected signal(s)")
assert len(rejected_signals) == 1
assert rejected_signals[0].decision_reason is not None
print(f"  reason logged: {rejected_signals[0].decision_reason}")

print("\n=== Case 2: accepted signal, full execution ===")
sl_price = round(mark_price * 0.97, 1)
result = execute_signal_with_logging(
    exchange, engine, SYMBOL, "M15", "LONG", "TREND",
    entry_price=mark_price, sl_price=sl_price, tp_price=None,
    risk_pct=0.02, equity=10_000, exchange_spec=exchange_spec,
)
print(f"Executed: qty={result['qty']}, signal_id={result['signal_id']}, trade_id={result['trade_id']}")

with engine.connect() as conn:
    sig = conn.execute(select(signals).where(signals.c.signal_id == result["signal_id"])).fetchone()
    rd = conn.execute(select(risk_decisions).where(risk_decisions.c.signal_id == result["signal_id"])).fetchone()
    ords = conn.execute(select(orders).where(orders.c.signal_id == result["signal_id"])).fetchall()
    trd = conn.execute(select(trades).where(trades.c.trade_id == result["trade_id"])).fetchone()

print(f"Signal row: action={sig.action}, decision={sig.decision}")
print(f"Risk decision row: accepted={rd.accepted}, computed_qty={rd.computed_qty}")
print(f"Order rows: {len(ords)} (expect 2: entry + sl)")
for o in ords:
    print(f"  type={o.order_type}, exchange_order_id={o.exchange_order_id}, algo_order_id={o.algo_order_id}")
print(f"Trade row: entry_price={trd.entry_price}, qty={trd.qty}, exit_time_utc={trd.exit_time_utc} (should be None, still open)")

assert sig.decision == "ACCEPTED"
assert rd.accepted is True
assert len(ords) == 2
assert trd.exit_time_utc is None
assert abs(trd.qty - result["qty"]) < 1e-9

print("\nPASS: DB records match exchange reality for both the rejected and accepted paths.")

print("\n--- Cleanup ---")
cancel_all_and_flatten(exchange, SYMBOL)
