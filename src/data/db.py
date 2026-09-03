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
    # historical-stats EV gate (§8, src/live/ev_estimate.py) — NOT ML,
    # see that module's docstring for why. Populated for every candidate
    # setup v0_rules triggers, null for regime-based NO_TRADE bars.
    Column("est_win_rate", Float, nullable=True),
    Column("expected_move_pct", Float, nullable=True),
    Column("trading_cost_pct", Float, nullable=True),
    Column("ev_r", Float, nullable=True),
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

# regime_states: written by src/regime/engine.py::classify_regime_v2 (5-class
# TREND/RANGE/VOLATILITY_EXPANSION/HIGH_VOLATILITY/UNKNOWN regime engine, XAU P4).
# Separate from the "regime" column on `signals` above, which is written by the
# locked 2-class src/regime/rules.py::classify_regime used by the live ETH/XRP
# pipeline -- do not conflate the two.
regime_states = Table(
    "regime_states", metadata,
    Column("symbol", String, primary_key=True),
    Column("timeframe", String, primary_key=True),
    Column("time_utc", DateTime(timezone=True), primary_key=True),
    Column("regime", String),
    Column("regime_confidence", Float),
    Column("regime_features", String),  # JSON
    Column("computed_at_utc", DateTime(timezone=True)),
)


# setups: durable snapshot of src/scanner/registry.py::REGISTRY (XAU P5) --
# written by sync_registry_to_db(), a queryable record for later phases
# (dashboard, promotion workflow). Not written to by any live path.
setups = Table(
    "setups", metadata,
    Column("setup_id", String, primary_key=True),
    Column("market", String), Column("category", String), Column("status", String),
    Column("entry_point", String), Column("evidence", String),
    Column("updated_at_utc", DateTime(timezone=True)),
)


def get_engine(db_path: str = "data/trading.db"):
    return create_engine(f"sqlite:///{db_path}")


def init_db(db_path: str = "data/trading.db"):
    engine = get_engine(db_path)
    metadata.create_all(engine)
    _migrate_add_missing_columns(engine)
    return engine


def _migrate_add_missing_columns(engine):
    """SQLite has no ALTER TABLE ADD COLUMN IF NOT EXISTS — for a DB file
    created before ev_estimate columns existed, add them idempotently
    (ignore "duplicate column" if they're already there)."""
    from sqlalchemy import text
    new_columns = [
        ("signals", "est_win_rate", "FLOAT"),
        ("signals", "expected_move_pct", "FLOAT"),
        ("signals", "trading_cost_pct", "FLOAT"),
        ("signals", "ev_r", "FLOAT"),
    ]
    with engine.begin() as conn:
        for table, col, coltype in new_columns:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"))
            except Exception:
                pass  # column already exists


if __name__ == "__main__":
    init_db()
    print("DB initialized at data/trading.db")
