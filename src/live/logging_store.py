"""Log-before-execute helpers — PROJECT_PLAN.md §2 ("log ก่อน execute เสมอ").

Every function here writes a DB row FIRST, then the caller makes the
exchange call. If the process dies between the two, the DB row is proof of
what was attempted — critical for reconciliation after a crash (§19).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import insert
from sqlalchemy.engine import Engine

from src.data.db import signals, risk_decisions, orders, trades


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def log_signal(engine: Engine, symbol: str, timeframe: str, action: str, regime: str,
                sl_price: float, tp_price: float, risk_pct: float, model_version: str = "v0_rules") -> str:
    signal_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(insert(signals).values(
            signal_id=signal_id, created_at_utc=now_utc(), symbol=symbol, timeframe=timeframe,
            action=action, regime=regime, suggested_sl=sl_price, suggested_tp=tp_price,
            suggested_risk_pct=risk_pct, model_version=model_version, decision=None, decision_reason=None,
        ))
    return signal_id


def log_risk_decision(engine: Engine, signal_id: str, accepted: bool, computed_qty: float,
                       equity_at_decision: float, reject_layer: str | None = None, reject_reason: str | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(insert(risk_decisions).values(
            signal_id=signal_id, received_at_utc=now_utc(), accepted=accepted,
            reject_layer=reject_layer, reject_reason=reject_reason,
            computed_qty=computed_qty, equity_at_decision=equity_at_decision,
        ))
        conn.execute(
            signals.update().where(signals.c.signal_id == signal_id).values(
                decision="ACCEPTED" if accepted else "REJECTED",
                decision_reason=reject_reason,
            )
        )


def log_order(engine: Engine, signal_id: str, exchange_order_id: str, order_type: str,
              side: str, qty: float, price: float | None, status: str, algo_order_id: str | None = None) -> str:
    order_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(insert(orders).values(
            order_id=order_id, signal_id=signal_id, sent_at_utc=now_utc(),
            exchange_order_id=exchange_order_id, algo_order_id=algo_order_id,
            order_type=order_type, side=side, qty=qty, price=price, status=status,
        ))
    return order_id


def log_trade_open(engine: Engine, signal_id: str, symbol: str, entry_price: float,
                    qty: float, sl_price: float, tp_price: float | None) -> str:
    trade_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(insert(trades).values(
            trade_id=trade_id, signal_id=signal_id, symbol=symbol,
            entry_time_utc=now_utc(), entry_price=entry_price, qty=qty,
            sl_price=sl_price, tp_price=tp_price,
            exit_time_utc=None, exit_price=None, exit_reason=None, net_pnl=None, r_multiple=None,
        ))
    return trade_id


def log_trade_close(engine: Engine, trade_id: str, exit_price: float, exit_reason: str,
                     net_pnl: float, r_multiple: float) -> None:
    with engine.begin() as conn:
        conn.execute(
            trades.update().where(trades.c.trade_id == trade_id).values(
                exit_time_utc=now_utc(), exit_price=exit_price, exit_reason=exit_reason,
                net_pnl=net_pnl, r_multiple=r_multiple,
            )
        )
