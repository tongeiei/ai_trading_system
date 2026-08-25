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

from sqlalchemy import select

from src.data.db import init_db, trades as trades_table
from src.live.signal_service import generate_live_signal
from src.live.order_executor import execute_signal_with_logging, OrderRejected
from src.live.reconcile import reconcile_symbol
from src.live.logging_store import log_signal
from src.live.guards import heartbeat_guard, rolling_winrate_risk_multiplier
from src.live.position_timeout import close_expired_positions
from src.live.ev_estimate import estimate_ev
from src.risk.sizing import ExchangeSpec

SYMBOL = "ETH/USDT:USDT"
LOCKED_CONFIG = {"adx": 35, "sl": 2.5}
# 0.5%, not the originally-planned 1-2% — lowered per docs/FINDINGS.md after
# walk-forward showed the ETH edge is real but unstable (2023 H2 was
# significantly negative, a regime the single train/holdout split missed).
BASE_RISK_PCT = 0.005
WINRATE_WINDOW = 20
WINRATE_THRESHOLD = 0.30
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

    # close anything that's been open >12h before doing anything else — mirrors
    # triple_barrier.MAX_HOLD_BARS_M1, see position_timeout.py docstring for
    # why this can't be an exchange-native order and has to be checked here
    closed = close_expired_positions(exchange, engine, SYMBOL)
    if closed:
        print(f"Closed {len(closed)} expired position(s) via timeout.")

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

    # §8 EV gate — historical-stats based (NOT ML, see ev_estimate.py docstring).
    # sl_distance is computed by v0_rules for every bar regardless of action,
    # so this can run even for candidates that later get downgraded here.
    ev = None
    original_action = latest["action"]
    if original_action != "NO_TRADE":
        ev = estimate_ev(float(latest["close"]), float(latest["sl_distance"]))
        print(f"EV check: win_rate={ev.win_rate:.1%} expected_move={ev.expected_move_pct:+.3f}% "
              f"trading_cost={-ev.trading_cost_pct:.3f}% ev={ev.ev_r:+.3f}R -> "
              f"{'PASS' if ev.passes_gate else 'REJECTED (cost > edge)'}")
        if not ev.passes_gate:
            latest = latest.copy()
            latest["action"] = "NO_TRADE"

    # §19 early-warning: check the last WINRATE_WINDOW closed trades before
    # sizing this one — a win rate this low showed up in the 2023-H2 walk-forward
    # fold well before any DD/daily-loss threshold would have reacted.
    with engine.connect() as conn:
        recent_closed = conn.execute(
            select(trades_table.c.r_multiple)
            .where(trades_table.c.r_multiple.isnot(None))
            .order_by(trades_table.c.exit_time_utc.asc())
        ).fetchall()
    recent_r = [row.r_multiple for row in recent_closed]
    risk_multiplier = rolling_winrate_risk_multiplier(recent_r, window=WINRATE_WINDOW, winrate_threshold=WINRATE_THRESHOLD)
    risk_pct = BASE_RISK_PCT * risk_multiplier
    if risk_multiplier < 1.0:
        recent_winrate = sum(1 for r in recent_r[-WINRATE_WINDOW:] if r > 0) / min(len(recent_r), WINRATE_WINDOW)
        print(f"WARNING: last {WINRATE_WINDOW} trades win rate {recent_winrate:.0%} < {WINRATE_THRESHOLD:.0%} "
              f"— risk cut to {risk_pct:.3%} (x{risk_multiplier})")

    signal_id = log_signal(
        engine, SYMBOL, "M15", latest["action"], latest["regime"],
        float(latest["sl_price"]) if latest["action"] != "NO_TRADE" else None,
        float(latest["tp_price"]) if latest["action"] != "NO_TRADE" else None,
        risk_pct, ev=ev,
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
            tp_price=float(latest["tp_price"]), risk_pct=risk_pct, equity=equity,
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
