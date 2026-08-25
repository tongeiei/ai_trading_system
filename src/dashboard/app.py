"""Minimal ops dashboard — PROJECT_PLAN.md §18, brought forward from P8 to
now because Phase B needs to be observable while it runs unattended.

Reads directly from the SQLite DB the live signal cycle writes to — no
separate data pipeline, so there's nothing to keep in sync.

Run: streamlit run src/dashboard/app.py
"""
import sys
import time
from pathlib import Path

import ccxt
import pandas as pd
import streamlit as st
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.db import get_engine
DB_PATH = str(PROJECT_ROOT / "data" / "trading.db")
HEARTBEAT_PATH = PROJECT_ROOT / "data" / "heartbeat.txt"
CHART_SYMBOL = "ETH/USDT:USDT"

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

signals_df = load_table("SELECT * FROM signals ORDER BY created_at_utc DESC")
trades_df = load_table("SELECT * FROM trades ORDER BY entry_time_utc DESC")
risk_df = load_table("SELECT * FROM risk_decisions ORDER BY received_at_utc DESC")

open_trades = trades_df[trades_df["exit_time_utc"].isna()] if len(trades_df) else pd.DataFrame()
closed_trades_all = trades_df[trades_df["exit_time_utc"].notna()] if len(trades_df) else pd.DataFrame()


@st.cache_data(ttl=30)
def fetch_last_price(symbol: str) -> float | None:
    try:
        exchange = ccxt.binanceusdm({"enableRateLimit": True})
        return float(exchange.fetch_ticker(symbol)["last"])
    except Exception:
        return None


last_price = fetch_last_price(CHART_SYMBOL)

# unrealized PnL for open positions (single-symbol system — direction inferred from SL vs entry)
unrealized_pnl = 0.0
if len(open_trades) and last_price is not None:
    for _, t in open_trades.iterrows():
        is_long = t["sl_price"] < t["entry_price"]
        diff = (last_price - t["entry_price"]) if is_long else (t["entry_price"] - last_price)
        unrealized_pnl += diff * t["qty"]

realized_all_time = closed_trades_all["net_pnl"].sum() if len(closed_trades_all) else 0.0

today_utc = pd.Timestamp.now(tz="UTC").normalize()
realized_today = 0.0
if len(closed_trades_all):
    exit_dates = pd.to_datetime(closed_trades_all["exit_time_utc"], utc=True).dt.normalize()
    realized_today = closed_trades_all.loc[exit_dates == today_utc, "net_pnl"].sum()

closed_with_r = closed_trades_all[closed_trades_all["r_multiple"].notna()] if len(closed_trades_all) else pd.DataFrame()
win_rate = (closed_with_r["r_multiple"] > 0).mean() if len(closed_with_r) else None

if HEARTBEAT_PATH.exists():
    last_beat = float(HEARTBEAT_PATH.read_text().strip())
    age_sec = time.time() - last_beat
    heartbeat_status = "🟢 live" if age_sec < 20 * 60 else "🔴 stale"  # signal cycle runs every 15min, allow slack
    st.caption(f"{heartbeat_status} · heartbeat {age_sec/60:.1f} min ago · {CHART_SYMBOL}"
               + (f" @ {last_price:.2f}" if last_price is not None else ""))
else:
    st.caption("⚪ heartbeat never run")

# --- Summary stat cards (Realized / Unrealized / Total P&L / Open / Closed / Win rate) ---
r1c1, r1c2 = st.columns(2)
r1c1.metric("Realized วันนี้", f"${realized_today:+,.2f}")
r1c2.metric("Unrealized", f"${unrealized_pnl:+,.2f}")

r2c1, r2c2 = st.columns(2)
r2c1.metric("P&L รวม", f"${(realized_all_time + unrealized_pnl):+,.2f}")
r2c2.metric("ถืออยู่", len(open_trades))

r3c1, r3c2 = st.columns(2)
r3c1.metric("ปิดแล้ว", len(closed_trades_all))
r3c2.metric("Win rate", f"{win_rate:.0%}" if win_rate is not None else "n/a")

st.info(
    f"💰 P&L รวมตั้งแต่เริ่มรัน = realized ${realized_all_time:+,.2f} "
    f"({len(closed_trades_all)} ไม้) + floating ${unrealized_pnl:+,.2f} ({len(open_trades)} ไม้)"
)

st.divider()

# --- Open positions table ---
st.subheader("ไม้เปิด")
if len(open_trades) > 0:
    open_view = open_trades.copy()
    if last_price is not None:
        def _upnl_pct(row):
            is_long = row["sl_price"] < row["entry_price"]
            diff_pct = (last_price - row["entry_price"]) / row["entry_price"] * 100
            return diff_pct if is_long else -diff_pct
        open_view["now"] = last_price
        open_view["uPnL%"] = open_view.apply(_upnl_pct, axis=1)
    st.dataframe(
        open_view[["trade_id", "symbol", "entry_time_utc", "entry_price"]
                   + (["now", "uPnL%"] if last_price is not None else [])
                   + ["qty", "sl_price", "tp_price"]],
        use_container_width=True, hide_index=True,
    )
else:
    st.info("ไม่มีไม้เปิดอยู่")

st.divider()

# --- Latest signal EV panel ---
# Historical-stats based (ETH backtest CAL fold), NOT an ML probability —
# the ML model was dropped at the P5 gate (AUC ~0.497 on holdout, see
# docs/FINDINGS.md). Labeled honestly to avoid implying a capability that
# doesn't exist.
st.subheader("Latest signal")
if len(signals_df) > 0:
    latest_signal = signals_df.iloc[0]
    if pd.notna(latest_signal.get("ev_r")):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Historical win rate", f"{latest_signal['est_win_rate']:.0%}")
        c2.metric("Expected move", f"{latest_signal['expected_move_pct']:+.3f}%")
        c3.metric("Trading cost", f"{-abs(latest_signal['trading_cost_pct']):.3f}%")
        gate_passed = latest_signal["ev_r"] >= 0.15
        c4.metric("EV (R)", f"{latest_signal['ev_r']:+.3f}R", "PASS" if gate_passed else "below threshold")
        st.caption("Based on ETH backtest historical base rate — not an ML prediction (see docs/FINDINGS.md, P5 gate).")
        final_action = latest_signal["action"] if latest_signal["decision"] != "REJECTED" else "NO_TRADE"
        st.markdown(f"**→ {final_action}**" + ("" if gate_passed or final_action == "NO_TRADE" else " (EV gate rejected)"))
    else:
        st.info(f"Latest bar: regime={latest_signal['regime']}, action=NO_TRADE (no candidate setup — nothing to score).")
else:
    st.info("No signals logged yet.")

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
    filtered_signals[["created_at_utc", "symbol", "action", "regime", "decision", "decision_reason",
                       "est_win_rate", "expected_move_pct", "trading_cost_pct", "ev_r"]].head(200),
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
