"""DB schema (SQLite) — PROJECT_PLAN.md §13, adapted for crypto.

signals/risk_decisions/orders/trades added for §16 Phase A: every live order
attempt (accepted or rejected) must be logged BEFORE the exchange call is
made (§2 principle: "log ก่อน execute เสมอ") — if the process dies between
logging and the exchange response, we still know what we attempted.
"""
from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, create_engine,
)

metadata = MetaData()

bars = Table(
    "bars", metadata,
    Column("symbol", String, primary_key=True),
    Column("timeframe", String, primary_key=True),
    Column("time_utc", DateTime(timezone=True), primary_key=True),
    Column("open", Float), Column("high", Float),
    Column("low", Float), Column("close", Float),
    Column("volume", Float),
)

funding_rates = Table(
    "funding_rates", metadata,
    Column("symbol", String, primary_key=True),
    Column("time_utc", DateTime(timezone=True), primary_key=True),
    Column("funding_rate", Float),
)


signals = Table(
    "signals", metadata,
    Column("signal_id", String, primary_key=True),
    Column("created_at_utc", DateTime(timezone=True)),
    Column("symbol", String), Column("timeframe", String),
    Column("action", String),  # LONG/SHORT/NO_TRADE
    Column("regime", String),
    Column("suggested_sl", Float), Column("suggested_tp", Float),
    Column("suggested_risk_pct", Float),
    Column("model_version", String),
    Column("decision", String),          # ACCEPTED/REJECTED
    Column("decision_reason", String),
)

risk_decisions = Table(
    "risk_decisions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("signal_id", String),
    Column("received_at_utc", DateTime(timezone=True)),
    Column("accepted", Boolean),
    Column("reject_layer", String),   # L0-L7 per §9.1, null if accepted
    Column("reject_reason", String),
    Column("computed_qty", Float),
    Column("equity_at_decision", Float),
)

orders = Table(
    "orders", metadata,
    Column("order_id", String, primary_key=True),
    Column("signal_id", String),
    Column("sent_at_utc", DateTime(timezone=True)),
    Column("exchange_order_id", String),
    Column("algo_order_id", String, nullable=True),  # SL order id — see order_executor.py docstring
    Column("order_type", String),  # entry/sl
    Column("side", String), Column("qty", Float), Column("price", Float),
    Column("status", String),
)

trades = Table(
    "trades", metadata,
    Column("trade_id", String, primary_key=True),
    Column("signal_id", String),
    Column("symbol", String),
    Column("entry_time_utc", DateTime(timezone=True)), Column("entry_price", Float),
    Column("exit_time_utc", DateTime(timezone=True), nullable=True), Column("exit_price", Float, nullable=True),
    Column("qty", Float),
    Column("sl_price", Float), Column("tp_price", Float, nullable=True),
    Column("exit_reason", String, nullable=True),  # TP/SL/manual/timeout/failsafe
    Column("net_pnl", Float, nullable=True), Column("r_multiple", Float, nullable=True),
)


def get_engine(db_path: str = "data/trading.db"):
    return create_engine(f"sqlite:///{db_path}")


def init_db(db_path: str = "data/trading.db"):
    engine = get_engine(db_path)
    metadata.create_all(engine)
    return engine


if __name__ == "__main__":
    init_db()
    print("DB initialized at data/trading.db")
