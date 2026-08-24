"""Reconciliation loop — PROJECT_PLAN.md §19.

Runs every 60s in production (§25 RiskState.mqh equivalent for crypto):
compares actual exchange state against what our records expect. The most
dangerous failure mode this catches is an ORPHAN POSITION — a position open
on the exchange with no protective SL — which must page CRITICAL and force-
close per §19.

Must check BOTH regular orders and algo/conditional orders (see
order_executor.py docstring — a naive check using only fetch_open_orders
will miss real SL orders and false-alarm).
"""
from dataclasses import dataclass, field

import ccxt

from src.live.order_executor import fetch_open_algo_orders


@dataclass
class ReconcileResult:
    symbol: str
    has_position: bool
    position_contracts: float
    has_protective_sl: bool
    orphan_position: bool  # position with NO SL — CRITICAL per §19
    orphan_sl: bool         # SL order with NO position behind it — cancel it, low severity
    severity: str = "OK"
    detail: str = ""


def reconcile_symbol(exchange: ccxt.Exchange, symbol: str) -> ReconcileResult:
    positions = exchange.fetch_positions([symbol])
    open_pos = [p for p in positions if abs(p.get("contracts") or 0) > 0]
    has_position = len(open_pos) > 0
    position_contracts = open_pos[0]["contracts"] if has_position else 0.0

    algo_orders = fetch_open_algo_orders(exchange, symbol)
    active_sl_orders = [a for a in algo_orders if a["algoStatus"] == "NEW" and a["orderType"] == "STOP_MARKET"]
    has_protective_sl = len(active_sl_orders) > 0

    orphan_position = has_position and not has_protective_sl
    orphan_sl = has_protective_sl and not has_position

    if orphan_position:
        return ReconcileResult(
            symbol, has_position, position_contracts, has_protective_sl,
            orphan_position=True, orphan_sl=False, severity="CRITICAL",
            detail="Position open with NO protective SL — force-close immediately per §19.",
        )
    if orphan_sl:
        return ReconcileResult(
            symbol, has_position, position_contracts, has_protective_sl,
            orphan_position=False, orphan_sl=True, severity="WARN",
            detail="SL order exists with no position behind it — likely stale, safe to cancel.",
        )
    return ReconcileResult(
        symbol, has_position, position_contracts, has_protective_sl,
        orphan_position=False, orphan_sl=False, severity="OK",
        detail="protected position" if has_position else "flat, no open orders",
    )
