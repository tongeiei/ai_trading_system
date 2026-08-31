from sqlalchemy import select

from src.data.db import init_db, signals, risk_decisions, orders, trades
from src.live.logging_store import (
    log_signal, log_risk_decision, log_order, log_trade_open, log_trade_close,
    consecutive_ev_gate_rejections,
)


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


def test_recent_closed_r_multiples_filters_by_symbol_ordered(tmp_path):
    from src.live.logging_store import recent_closed_r_multiples
    engine = make_test_engine(tmp_path)

    # ETH: two closed trades (should come back in exit-time order) + one still open
    sid = log_signal(engine, "ETH/USDT:USDT", "M15", "LONG", "TREND", 2400.0, 2600.0, 0.01)
    t1 = log_trade_open(engine, sid, "ETH/USDT:USDT", 2500.0, 0.05, 2400.0, 2600.0)
    log_trade_close(engine, t1, 2600.0, "TP", net_pnl=5.0, r_multiple=2.0)
    t2 = log_trade_open(engine, sid, "ETH/USDT:USDT", 2500.0, 0.05, 2400.0, 2600.0)
    log_trade_close(engine, t2, 2400.0, "SL", net_pnl=-2.5, r_multiple=-1.0)
    log_trade_open(engine, sid, "ETH/USDT:USDT", 2500.0, 0.05, 2400.0, 2600.0)  # open, excluded

    # XRP: one closed trade — must NOT appear in ETH's history
    sidx = log_signal(engine, "XRP/USDT:USDT", "M15", "SHORT", "TREND", 0.55, 0.45, 0.01)
    tx = log_trade_open(engine, sidx, "XRP/USDT:USDT", 0.50, 100.0, 0.55, 0.45)
    log_trade_close(engine, tx, 0.45, "TP", net_pnl=5.0, r_multiple=2.0)

    assert recent_closed_r_multiples(engine, "ETH/USDT:USDT") == [2.0, -1.0]
    assert recent_closed_r_multiples(engine, "XRP/USDT:USDT") == [2.0]


def test_log_signal_records_no_trade_reason(tmp_path):
    """A NO_TRADE row must say WHY. 'no setup' and 'setup rejected by the EV
    gate' are operationally very different — one is a quiet market, the other
    means the strategy is structurally unable to trade — and before this they
    were indistinguishable in the DB (both just action=NO_TRADE, decision=None).
    """
    engine = make_test_engine(tmp_path)
    no_setup = log_signal(engine, "ETH/USDT:USDT", "M15", "NO_TRADE", "RANGE", None, None, 0.005,
                          decision="NO_SETUP", decision_reason="v0_rules: no entry condition met")
    gated = log_signal(engine, "ETH/USDT:USDT", "M15", "NO_TRADE", "TREND", None, None, 0.005,
                       decision="REJECTED", decision_reason="EV gate: ev=+0.004R < 0.150R")

    with engine.connect() as conn:
        rows = {r.signal_id: r for r in conn.execute(select(signals)).fetchall()}
    assert rows[no_setup].decision == "NO_SETUP"
    assert rows[gated].decision == "REJECTED"
    assert "EV gate" in rows[gated].decision_reason


def test_consecutive_ev_gate_rejections_counts_only_since_last_trade(tmp_path):
    engine = make_test_engine(tmp_path)
    for _ in range(3):
        log_signal(engine, "ETH/USDT:USDT", "M15", "NO_TRADE", "TREND", None, None, 0.005,
                   decision="REJECTED", decision_reason="EV gate: ev=+0.004R < 0.150R")
    # a NO_SETUP bar in between must not reset the streak — it is not a rejected setup
    log_signal(engine, "ETH/USDT:USDT", "M15", "NO_TRADE", "RANGE", None, None, 0.005,
               decision="NO_SETUP", decision_reason="v0_rules: no entry condition met")
    # another symbol's rejections must not leak into this symbol's count
    log_signal(engine, "XRP/USDT:USDT", "M15", "NO_TRADE", "TREND", None, None, 0.0025,
               decision="REJECTED", decision_reason="EV gate: ev=+0.010R < 0.150R")

    assert consecutive_ev_gate_rejections(engine, "ETH/USDT:USDT") == 3
    assert consecutive_ev_gate_rejections(engine, "XRP/USDT:USDT") == 1


def test_consecutive_ev_gate_rejections_resets_after_an_accepted_signal(tmp_path):
    engine = make_test_engine(tmp_path)
    for _ in range(2):
        log_signal(engine, "ETH/USDT:USDT", "M15", "NO_TRADE", "TREND", None, None, 0.005,
                   decision="REJECTED", decision_reason="EV gate: ev=+0.004R < 0.150R")
    taken = log_signal(engine, "ETH/USDT:USDT", "M15", "LONG", "TREND", 2400.0, 2600.0, 0.005)
    log_risk_decision(engine, taken, accepted=True, computed_qty=0.05, equity_at_decision=10_000)
    log_signal(engine, "ETH/USDT:USDT", "M15", "NO_TRADE", "TREND", None, None, 0.005,
               decision="REJECTED", decision_reason="EV gate: ev=+0.004R < 0.150R")

    assert consecutive_ev_gate_rejections(engine, "ETH/USDT:USDT") == 1
