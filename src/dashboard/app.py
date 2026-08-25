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
import plotly.graph_objects as go
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

# --- Candlestick chart with trade markers ---
st.subheader(f"Price chart — {CHART_SYMBOL} (M15)")


@st.cache_data(ttl=60)
def fetch_recent_candles(symbol: str, n_bars: int = 200) -> pd.DataFrame:
    exchange = ccxt.binanceusdm({"enableRateLimit": True})
    exchange.load_markets()
    raw = exchange.fetch_ohlcv(symbol, timeframe="15m", limit=n_bars)
    df = pd.DataFrame(raw, columns=["ts_ms", "open", "high", "low", "close", "volume"])
    df["time_utc"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    return df.drop(columns=["ts_ms"])


try:
    candles = fetch_recent_candles(CHART_SYMBOL)
    fig = go.Figure(data=[go.Candlestick(
        x=candles["time_utc"], open=candles["open"], high=candles["high"],
        low=candles["low"], close=candles["close"], name=CHART_SYMBOL,
    )])

    # overlay trades that fall within the visible window
    chart_start, chart_end = candles["time_utc"].min(), candles["time_utc"].max()
    visible_trades = trades_df[
        (pd.to_datetime(trades_df["entry_time_utc"], utc=True) >= chart_start) &
        (pd.to_datetime(trades_df["entry_time_utc"], utc=True) <= chart_end)
    ] if len(trades_df) else pd.DataFrame()

    for _, t in visible_trades.iterrows():
        is_long = t["sl_price"] < t["entry_price"]
        entry_time = pd.to_datetime(t["entry_time_utc"], utc=True)
        fig.add_trace(go.Scatter(
            x=[entry_time], y=[t["entry_price"]], mode="markers",
            marker=dict(symbol="triangle-up" if is_long else "triangle-down", size=14,
                        color="lime" if is_long else "red"),
            name=f"{'LONG' if is_long else 'SHORT'} entry", showlegend=False,
            hovertext=f"{'LONG' if is_long else 'SHORT'} @ {t['entry_price']:.2f}",
        ))
        if pd.notna(t["exit_time_utc"]):
            exit_time = pd.to_datetime(t["exit_time_utc"], utc=True)
            fig.add_trace(go.Scatter(
                x=[exit_time], y=[t["exit_price"]], mode="markers",
                marker=dict(symbol="x", size=12,
                            color="lime" if (t["r_multiple"] or 0) > 0 else "red"),
                name="exit", showlegend=False,
                hovertext=f"exit {t['exit_reason']} @ {t['exit_price']:.2f} ({t['r_multiple']:+.2f}R)",
            ))

    fig.update_layout(
        height=500, xaxis_rangeslider_visible=False,
        template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("▲ green = LONG entry · ▼ red = SHORT entry · ✕ = exit (green=win, red=loss). Last 200 M15 bars, live from exchange.")
except Exception as e:
    st.warning(f"Could not fetch live chart data: {e}")

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
