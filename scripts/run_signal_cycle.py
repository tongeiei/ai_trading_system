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
from src.live.logging_store import log_signal, recent_closed_r_multiples, consecutive_ev_gate_rejections
from src.live.guards import heartbeat_guard, rolling_winrate_risk_multiplier
from src.live.position_timeout import close_expired_positions, detect_and_close_organic_exits
from src.live.ev_estimate import estimate_ev, EV_THRESHOLD_R
from src.live.alerting import (
    alert_trade_opened, alert_trade_closed, alert_critical, alert_error, alert_gate_blocked,
)
from src.risk.sizing import ExchangeSpec

# Each entry is one independently-traded symbol. base_risk_pct is per-symbol so a
# weaker/less-proven candidate can run at reduced size without touching the anchor.
# ETH: 0.5% (not the planned 1-2%) — lowered per docs/FINDINGS.md after walk-forward
# showed the edge is real but unstable (2023 H2 was significantly negative).
SYMBOLS = [
    {"symbol": "ETH/USDT:USDT", "config": {"adx": 35, "sl": 2.5}, "base_risk_pct": 0.005},
    # XRP is a vetted but TIER-2 candidate (docs/FINDINGS.md 2026-08): a real but
    # fragile V0 edge (holdout PF 1.18, fails at 3x slippage), low strategy-return
    # correlation to ETH. Paper-trading (demo) at half ETH's risk while more
    # live data accumulates — not a live-capital decision, still demo trading.
    {"symbol": "XRP/USDT:USDT", "config": {"adx": 35, "sl": 2.5}, "base_risk_pct": 0.0025},
]
WINRATE_WINDOW = 20
# One M15 bar per cycle, so this is ~24h of consecutive gate rejections. Alerting
# on the streak (once, when it first crosses) is what makes "the strategy can no
# longer clear its own EV gate" visible — that state is otherwise indistinguishable
# from a quiet market in the logs, which is how a full week of zero trades went
# unnoticed (docs/research/BTC_EDGE_SEARCH.md Round 6 addendum).
EV_GATE_ALERT_STREAK = 96
WINRATE_THRESHOLD = 0.30
HEARTBEAT_PATH = PROJECT_ROOT / "data" / "heartbeat.txt"
DB_PATH = str(PROJECT_ROOT / "data" / "trading.db")


def write_heartbeat():
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.write_text(str(time.time()))


def run_symbol_cycle(exchange, public_exchange, engine, markets, symbol, config, base_risk_pct):
    """One symbol's full cycle. Isolated so one symbol's failure (a bad fetch,
    a rejected order) never blocks the others — main() catches per symbol."""
    spec = markets[symbol]
    print(f"\n--- {symbol} ---")

    # close anything that's been open >12h before doing anything else — mirrors
    # triple_barrier.MAX_HOLD_BARS_M1, see position_timeout.py docstring for
    # why this can't be an exchange-native order and has to be checked here
    closed = close_expired_positions(exchange, engine, symbol)
    if closed:
        print(f"Closed {len(closed)} expired position(s) via timeout.")
        for trade_id in closed:
            with engine.connect() as conn:
                t = conn.execute(select(trades_table).where(trades_table.c.trade_id == trade_id)).fetchone()
            alert_trade_closed(symbol, "TIMEOUT", t.exit_price, t.r_multiple)

    # detect SL/TP that already fired on the exchange — our process never
    # gets a callback for these, so this is the only way to notice
    organic_closes = detect_and_close_organic_exits(exchange, engine, symbol)
    for c in organic_closes:
        alert_trade_closed(symbol, c["exit_reason"], c["exit_price"], c["r_multiple"])

    # L4/§19: refuse to act if there's already an unprotected or unexpected position
    recon = reconcile_symbol(exchange, symbol)
    if recon.severity == "CRITICAL":
        print(f"CRITICAL: {recon.detail} — skipping this symbol, needs manual intervention.")
        alert_critical(f"{symbol}: {recon.detail}")
        return
    if recon.has_position:
        print(f"Position already open ({recon.position_contracts} contracts) — skipping, no pyramiding.")
        return

    signals = generate_live_signal(public_exchange, symbol, config["adx"], config["sl"])
    latest = signals.iloc[-1]

    print(f"Bar: {latest['time_utc']} | Regime: {latest['regime']} | Action: {latest['action']}")

    # §8 EV gate — historical-stats based (NOT ML, see ev_estimate.py docstring).
    # sl_distance is computed by v0_rules for every bar regardless of action,
    # so this can run even for candidates that later get downgraded here.
    ev = None
    no_trade_decision = None
    no_trade_reason = None
    original_action = latest["action"]
    if original_action == "NO_TRADE":
        no_trade_decision = "NO_SETUP"
        no_trade_reason = f"v0_rules: no entry condition met (regime={latest['regime']})"
    else:
        ev = estimate_ev(symbol, float(latest["close"]), float(latest["sl_distance"]))
        print(f"EV check: win_rate={ev.win_rate:.1%} expected_move={ev.expected_move_pct:+.3f}% "
              f"trading_cost={-ev.trading_cost_pct:.3f}% ev={ev.ev_r:+.3f}R -> "
              f"{'PASS' if ev.passes_gate else 'REJECTED (cost > edge)'}")
        if not ev.passes_gate:
            latest = latest.copy()
            latest["action"] = "NO_TRADE"
            no_trade_decision = "REJECTED"
            no_trade_reason = f"EV gate: ev={ev.ev_r:+.3f}R < {EV_THRESHOLD_R:.3f}R"

    # §19 early-warning: check the last WINRATE_WINDOW closed trades FOR THIS
    # SYMBOL before sizing — a win rate this low showed up in the 2023-H2
    # walk-forward fold well before any DD/daily-loss threshold would react.
    # Per-symbol so one symbol's slump doesn't throttle another's sizing.
    recent_r = recent_closed_r_multiples(engine, symbol)
    risk_multiplier = rolling_winrate_risk_multiplier(recent_r, window=WINRATE_WINDOW, winrate_threshold=WINRATE_THRESHOLD)
    risk_pct = base_risk_pct * risk_multiplier
    if risk_multiplier < 1.0:
        recent_winrate = sum(1 for r in recent_r[-WINRATE_WINDOW:] if r > 0) / min(len(recent_r), WINRATE_WINDOW)
        print(f"WARNING: last {WINRATE_WINDOW} {symbol} trades win rate {recent_winrate:.0%} < {WINRATE_THRESHOLD:.0%} "
              f"— risk cut to {risk_pct:.3%} (x{risk_multiplier})")

    log_signal(
        engine, symbol, "M15", latest["action"], latest["regime"],
        float(latest["sl_price"]) if latest["action"] != "NO_TRADE" else None,
        float(latest["tp_price"]) if latest["action"] != "NO_TRADE" else None,
        risk_pct, ev=ev, decision=no_trade_decision, decision_reason=no_trade_reason,
    )

    if latest["action"] == "NO_TRADE":
        print(f"No trade this cycle — {no_trade_reason}")
        if no_trade_decision == "REJECTED":
            streak = consecutive_ev_gate_rejections(engine, symbol)
            print(f"EV gate has now rejected {streak} consecutive {symbol} setup(s).")
            # fire once, on the cycle that crosses the line — re-alerting every
            # 15 min afterwards would train us to ignore it
            if streak == EV_GATE_ALERT_STREAK:
                alert_gate_blocked(symbol, streak, streak * 0.25, ev.ev_r, EV_THRESHOLD_R)
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
            exchange, engine, symbol, "M15", latest["action"], latest["regime"],
            entry_price=float(latest["close"]), sl_price=float(latest["sl_price"]),
            tp_price=float(latest["tp_price"]), risk_pct=risk_pct, equity=equity,
            exchange_spec=exchange_spec,
        )
        print(f"EXECUTED: qty={result['qty']}, trade_id={result['trade_id']}")
        alert_trade_opened(symbol, latest["action"], result["qty"], float(latest["close"]),
                            float(latest["sl_price"]), float(latest["tp_price"]), risk_pct)
    except OrderRejected as e:
        print(f"Order rejected: {e}")
        alert_error(f"{symbol} order rejected: {e}")


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

    # public data fetch doesn't need auth — one shared plain instance for all symbols
    public_exchange = ccxt.binanceusdm({"enableRateLimit": True})
    public_exchange.load_markets()

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}] cycle start "
          f"({len(SYMBOLS)} symbol(s))")

    for entry in SYMBOLS:
        symbol = entry["symbol"]
        try:
            run_symbol_cycle(exchange, public_exchange, engine, markets, symbol,
                             entry["config"], entry["base_risk_pct"])
        except Exception as e:
            # isolate: one symbol crashing must not stop the rest of the cycle
            print(f"ERROR in {symbol} cycle:")
            traceback.print_exc()
            alert_error(f"{symbol} cycle error: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("UNHANDLED EXCEPTION in signal cycle:")
        traceback.print_exc()
        alert_error(f"signal cycle crashed: {e}")
        raise
