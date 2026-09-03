"""Log-before-execute helpers — PROJECT_PLAN.md §2 ("log ก่อน execute เสมอ").

Every function here writes a DB row FIRST, then the caller makes the
exchange call. If the process dies between the two, the DB row is proof of
what was attempted — critical for reconciliation after a crash (§19).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import insert, select, text
from sqlalchemy.engine import Engine

from src.data.db import signals, risk_decisions, orders, trades, regime_states, scorecard_log


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


EV_GATE_REJECTION = "REJECTED"
NO_SETUP = "NO_SETUP"
EV_GATE_REASON_PREFIX = "EV gate:"


def log_signal(engine: Engine, symbol: str, timeframe: str, action: str, regime: str,
                sl_price: float, tp_price: float, risk_pct: float, model_version: str = "v0_rules",
                ev: "EVEstimate | None" = None, decision: str | None = None,
                decision_reason: str | None = None) -> str:
    """decision/decision_reason let a NO_TRADE row say WHY it was a NO_TRADE.

    Leave both None for a signal that goes on to the risk/execution path —
    log_risk_decision fills them in there. Pass them only for the terminal
    NO_TRADE cases, where nothing downstream will ever set them and the row
    would otherwise be indistinguishable from any other quiet bar.
    """
    signal_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(insert(signals).values(
            signal_id=signal_id, created_at_utc=now_utc(), symbol=symbol, timeframe=timeframe,
            action=action, regime=regime, suggested_sl=sl_price, suggested_tp=tp_price,
            suggested_risk_pct=risk_pct, model_version=model_version, decision=decision, decision_reason=decision_reason,
            est_win_rate=ev.win_rate if ev else None,
            expected_move_pct=ev.expected_move_pct if ev else None,
            trading_cost_pct=ev.trading_cost_pct if ev else None,
            ev_r=ev.ev_r if ev else None,
        ))
    return signal_id


def consecutive_ev_gate_rejections(engine: Engine, symbol: str) -> int:
    """How many EV-gate rejections for this symbol since the last ACCEPTED signal.

    Exists because a gate-rejected setup and an ordinary quiet bar both surface
    as "NO_TRADE" in the log, so a strategy that has become structurally unable
    to clear the gate looks exactly like a slow market — which is how a week of
    zero trades went unnoticed (docs/research/BTC_EDGE_SEARCH.md Round 6
    addendum). NO_SETUP rows are skipped rather than treated as a reset: they
    are not rejected setups, so they say nothing about whether the gate is
    passable.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            select(signals.c.decision, signals.c.decision_reason)
            .where(signals.c.symbol == symbol)
            .order_by(signals.c.created_at_utc.desc(), text("rowid DESC"))
        ).fetchall()

    count = 0
    for row in rows:
        if row.decision == "ACCEPTED":
            break
        if row.decision == EV_GATE_REJECTION and (row.decision_reason or "").startswith(EV_GATE_REASON_PREFIX):
            count += 1
    return count


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


def recent_closed_r_multiples(engine: Engine, symbol: str) -> list[float]:
    """Closed-trade r_multiples for ONE symbol, oldest→newest by exit time.

    Per-symbol so the rolling-winrate risk guard reacts to that symbol's own
    recent record — one symbol's losing streak must not throttle another's.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            select(trades.c.r_multiple)
            .where(trades.c.symbol == symbol)
            .where(trades.c.r_multiple.isnot(None))
            .order_by(trades.c.exit_time_utc.asc())
        ).fetchall()
    return [row.r_multiple for row in rows]


def log_trade_close(engine: Engine, trade_id: str, exit_price: float, exit_reason: str,
                     net_pnl: float, r_multiple: float) -> None:
    with engine.begin() as conn:
        conn.execute(
            trades.update().where(trades.c.trade_id == trade_id).values(
                exit_time_utc=now_utc(), exit_price=exit_price, exit_reason=exit_reason,
                net_pnl=net_pnl, r_multiple=r_multiple,
            )
        )


def log_scorecard_batch(engine: Engine, symbol: str, timeframe: str, scored_df) -> int:
    """Bulk-insert one row per trade from a scorecard-scored DataFrame (columns:
    strategy, time_utc, action, trend, structure, momentum, volatility, session,
    risk, final_score, weakest_link_block, decision, risk_pct, and optionally
    net_r_multiple/veto/veto_reason/thesis) -- see src.ai.scorecard and
    scripts/shadow_log_scorecard.py. Shadow-mode only: this never gates
    anything, it only records. Append-only, like the other log_* helpers here.

    Returns the number of rows inserted.
    """
    logged_at = now_utc()
    rows = [
        {
            "strategy": row.strategy, "symbol": symbol, "timeframe": timeframe,
            "time_utc": row.time_utc, "direction": row.action,
            "trend": row.trend, "structure": row.structure, "momentum": row.momentum,
            "volatility": row.volatility, "session": row.session, "risk": row.risk,
            "final_score": row.final_score, "weakest_link_block": bool(row.weakest_link_block),
            "decision": row.decision, "risk_pct": row.risk_pct,
            "veto": getattr(row, "veto", None), "veto_reason": getattr(row, "veto_reason", None),
            "thesis": getattr(row, "thesis", None),
            "actual_net_r_multiple": getattr(row, "net_r_multiple", None),
            "logged_at_utc": logged_at,
        }
        for row in scored_df.itertuples()
    ]
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(insert(scorecard_log), rows)
    return len(rows)


def log_regime_states(engine: Engine, symbol: str, timeframe: str, regime_df) -> int:
    """Bulk-insert one row per bar from src.regime.engine.classify_regime_v2's
    output. Append-only, like signals/trades -- not an upsert, so re-running
    against the same (symbol, timeframe, time_utc) range will raise an
    IntegrityError; use a fresh DB or a new symbol/timeframe per run.

    Returns the number of rows inserted.
    """
    computed_at = now_utc()
    rows = [
        {
            "symbol": symbol, "timeframe": timeframe, "time_utc": row.time_utc,
            "regime": row.regime, "regime_confidence": row.regime_confidence,
            "regime_features": row.regime_features, "computed_at_utc": computed_at,
        }
        for row in regime_df.itertuples()
    ]
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(insert(regime_states), rows)
    return len(rows)
