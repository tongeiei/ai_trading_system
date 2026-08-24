from sqlalchemy import select

from src.data.db import init_db, signals, risk_decisions, orders, trades
from src.live.logging_store import log_signal, log_risk_decision, log_order, log_trade_open, log_trade_close


def make_test_engine(tmp_path):
    return init_db(str(tmp_path / "test.db"))


def test_log_signal_then_risk_decision_updates_signal_row(tmp_path):
    engine = make_test_engine(tmp_path)
    signal_id = log_signal(engine, "ETH/USDT:USDT", "M15", "LONG", "TREND", 2400.0, 2600.0, 0.01)

    with engine.connect() as conn:
        row = conn.execute(select(signals).where(signals.c.signal_id == signal_id)).fetchone()
    assert row.decision is None  # not yet decided

    log_risk_decision(engine, signal_id, accepted=True, computed_qty=0.05, equity_at_decision=10_000)

    with engine.connect() as conn:
        row = conn.execute(select(signals).where(signals.c.signal_id == signal_id)).fetchone()
        rd = conn.execute(select(risk_decisions).where(risk_decisions.c.signal_id == signal_id)).fetchone()
    assert row.decision == "ACCEPTED"
    assert rd.accepted is True
    assert rd.computed_qty == 0.05


def test_log_rejected_signal_records_reason(tmp_path):
    engine = make_test_engine(tmp_path)
    signal_id = log_signal(engine, "ETH/USDT:USDT", "M15", "LONG", "TREND", 2400.0, 2600.0, 0.01)
    log_risk_decision(engine, signal_id, accepted=False, computed_qty=0.0, equity_at_decision=10,
                       reject_layer="L6_SIZING", reject_reason="below min notional")

    with engine.connect() as conn:
        row = conn.execute(select(signals).where(signals.c.signal_id == signal_id)).fetchone()
    assert row.decision == "REJECTED"
    assert row.decision_reason == "below min notional"


def test_full_flow_writes_order_and_trade_rows(tmp_path):
    engine = make_test_engine(tmp_path)
    signal_id = log_signal(engine, "ETH/USDT:USDT", "M15", "LONG", "TREND", 2400.0, 2600.0, 0.01)
    log_risk_decision(engine, signal_id, accepted=True, computed_qty=0.05, equity_at_decision=10_000)
    order_id = log_order(engine, signal_id, "ex-order-1", "entry", "buy", 0.05, 2500.0, "closed")
    trade_id = log_trade_open(engine, signal_id, "ETH/USDT:USDT", 2500.0, 0.05, 2400.0, 2600.0)

    with engine.connect() as conn:
        o = conn.execute(select(orders).where(orders.c.order_id == order_id)).fetchone()
        t = conn.execute(select(trades).where(trades.c.trade_id == trade_id)).fetchone()
    assert o.exchange_order_id == "ex-order-1"
    assert t.exit_time_utc is None  # still open

    log_trade_close(engine, trade_id, exit_price=2550.0, exit_reason="TP", net_pnl=2.5, r_multiple=0.5)
    with engine.connect() as conn:
        t = conn.execute(select(trades).where(trades.c.trade_id == trade_id)).fetchone()
    assert t.exit_reason == "TP"
    assert t.r_multiple == 0.5
