"""One-shot signal cycle — meant to be triggered every M15 bar-close by
systemd timer (see deploy/signal-cycle.timer). Each run:

  1. writes a heartbeat (proves the cycle is alive — §19 heartbeat_guard)
  2. checks for an orphan position first (§19 reconciliation) — refuses to
     trade if one exists, since that means something is already wrong
  3. generates a live signal from the locked ETH config
  4. logs the signal to DB regardless of action (§2 — log everything, not
     just trades taken)
  5. if action != NO_TRADE and no position is currently open, executes on
     the exchange (demo trading — no real money at this stage) with full
     risk-sizing + logging

This does NOT run continuously — systemd timer fires it once per interval,
which is simpler to reason about and restart-safe than a long-lived loop.
"""
import os
import sys
import time
import traceback
from pathlib import Path

import ccxt
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.data.db import init_db
from src.live.signal_service import generate_live_signal
from src.live.order_executor import execute_signal_with_logging, OrderRejected
from src.live.reconcile import reconcile_symbol
from src.live.logging_store import log_signal
from src.live.guards import heartbeat_guard
from src.risk.sizing import ExchangeSpec

SYMBOL = "ETH/USDT:USDT"
LOCKED_CONFIG = {"adx": 35, "sl": 2.5}
RISK_PCT = 0.01  # 1% — conservative, per §9.2 "start low until calibration proves itself"
HEARTBEAT_PATH = PROJECT_ROOT / "data" / "heartbeat.txt"
DB_PATH = str(PROJECT_ROOT / "data" / "trading.db")


def write_heartbeat():
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.write_text(str(time.time()))


def main():
    write_heartbeat()
    engine = init_db(DB_PATH)

    exchange = ccxt.binanceusdm({
        "apiKey": os.getenv("BINANCE_TESTNET_API_KEY"),
        "secret": os.getenv("BINANCE_TESTNET_API_SECRET"),
        "enableRateLimit": True,
    })
    exchange.enable_demo_trading(True)
    markets = exchange.load_markets()
    spec = markets[SYMBOL]

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}] cycle start")

    # L4/§19: refuse to act if there's already an unprotected or unexpected position
    recon = reconcile_symbol(exchange, SYMBOL)
    if recon.severity == "CRITICAL":
        print(f"CRITICAL: {recon.detail} — skipping this cycle, needs manual intervention.")
        return
    if recon.has_position:
        print(f"Position already open ({recon.position_contracts} contracts) — skipping, no pyramiding.")
        return

    # public data fetch doesn't need auth — use a plain instance for market data
    public_exchange = ccxt.binanceusdm({"enableRateLimit": True})
    public_exchange.load_markets()
    signals = generate_live_signal(public_exchange, SYMBOL, LOCKED_CONFIG["adx"], LOCKED_CONFIG["sl"])
    latest = signals.iloc[-1]

    print(f"Bar: {latest['time_utc']} | Regime: {latest['regime']} | Action: {latest['action']}")

    signal_id = log_signal(
        engine, SYMBOL, "M15", latest["action"], latest["regime"],
        float(latest["sl_price"]) if latest["action"] != "NO_TRADE" else None,
        float(latest["tp_price"]) if latest["action"] != "NO_TRADE" else None,
        RISK_PCT,
    )

    if latest["action"] == "NO_TRADE":
        print("No trade this cycle.")
        return

    balance = exchange.fetch_balance()
    equity = balance.get("USDT", {}).get("total") or 0.0
    exchange_spec = ExchangeSpec(
        amount_step=spec["precision"]["amount"],
        amount_min=spec["limits"]["amount"]["min"],
        min_notional=spec["limits"]["cost"]["min"],
    )

    try:
        result = execute_signal_with_logging(
            exchange, engine, SYMBOL, "M15", latest["action"], latest["regime"],
            entry_price=float(latest["close"]), sl_price=float(latest["sl_price"]),
            tp_price=float(latest["tp_price"]), risk_pct=RISK_PCT, equity=equity,
            exchange_spec=exchange_spec,
        )
        print(f"EXECUTED: qty={result['qty']}, trade_id={result['trade_id']}")
    except OrderRejected as e:
        print(f"Order rejected: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("UNHANDLED EXCEPTION in signal cycle:")
        traceback.print_exc()
        raise
