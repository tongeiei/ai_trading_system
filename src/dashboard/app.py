"""Minimal ops dashboard — PROJECT_PLAN.md §18, brought forward from P8 to
now because Phase B needs to be observable while it runs unattended.

Reads directly from the SQLite DB the live signal cycle writes to — no
separate data pipeline, so there's nothing to keep in sync.

Run: streamlit run src/dashboard/app.py
"""
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.db import get_engine
DB_PATH = str(PROJECT_ROOT / "data" / "trading.db")
HEARTBEAT_PATH = PROJECT_ROOT / "data" / "heartbeat.txt"

st.set_page_config(page_title="AI Trading System — Ops Dashboard", layout="wide")


@st.cache_resource
def get_db_engine():
    return get_engine(DB_PATH)


def load_table(query: str) -> pd.DataFrame:
    engine = get_db_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)


st.title("AI Trading System — Ops Dashboard")
st.caption(f"Reading from `{DB_PATH}`")

# --- System health row ---
col1, col2, col3, col4 = st.columns(4)

if HEARTBEAT_PATH.exists():
    last_beat = float(HEARTBEAT_PATH.read_text().strip())
    age_sec = time.time() - last_beat
    heartbeat_status = "🟢 alive" if age_sec < 20 * 60 else "🔴 stale"  # signal cycle runs every 15min, allow slack
    col1.metric("Heartbeat", heartbeat_status, f"{age_sec/60:.1f} min ago")
else:
    col1.metric("Heartbeat", "⚪ never run")

signals_df = load_table("SELECT * FROM signals ORDER BY created_at_utc DESC")
trades_df = load_table("SELECT * FROM trades ORDER BY entry_time_utc DESC")
risk_df = load_table("SELECT * FROM risk_decisions ORDER BY received_at_utc DESC")

col2.metric("Total signals logged", len(signals_df))
col3.metric("Trades taken", len(trades_df))
open_trades = trades_df[trades_df["exit_time_utc"].isna()] if len(trades_df) else pd.DataFrame()
col4.metric("Open positions", len(open_trades))

st.divider()

# --- Equity curve ---
st.subheader("Equity curve (cumulative R)")
closed_trades = trades_df[trades_df["r_multiple"].notna()] if len(trades_df) else pd.DataFrame()
if len(closed_trades) > 0:
    closed_trades = closed_trades.sort_values("entry_time_utc").copy()
    closed_trades["cumulative_r"] = closed_trades["r_multiple"].cumsum()
    st.line_chart(closed_trades.set_index("entry_time_utc")["cumulative_r"])
else:
    st.info("No closed trades yet — nothing to plot.")

# --- Trades table ---
st.subheader("Trades")
if len(trades_df) > 0:
    st.dataframe(
        trades_df[["trade_id", "symbol", "entry_time_utc", "entry_price", "qty",
                   "sl_price", "exit_time_utc", "exit_price", "exit_reason", "r_multiple"]],
        use_container_width=True, hide_index=True,
    )
else:
    st.info("No trades yet.")

# --- Signals log (including NO_TRADE and rejected) ---
st.subheader("Signal log")
action_filter = st.multiselect(
    "Filter by action", options=["LONG", "SHORT", "NO_TRADE"],
    default=["LONG", "SHORT", "NO_TRADE"],
)
filtered_signals = signals_df[signals_df["action"].isin(action_filter)] if len(signals_df) else signals_df
st.dataframe(
    filtered_signals[["created_at_utc", "symbol", "action", "regime", "decision", "decision_reason"]].head(200),
    use_container_width=True, hide_index=True,
)

# --- Risk decisions (rejections especially) ---
st.subheader("Risk decisions")
rejected = risk_df[risk_df["accepted"] == False] if len(risk_df) else pd.DataFrame()
st.metric("Rejected signals", len(rejected))
if len(risk_df) > 0:
    st.dataframe(
        risk_df[["received_at_utc", "accepted", "reject_layer", "reject_reason", "computed_qty", "equity_at_decision"]].head(100),
        use_container_width=True, hide_index=True,
    )
