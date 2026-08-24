"""§16 acceptance: "live signal ตรงกับ backtest replay 100%"

Freshly fetches OHLCV via the exchange API (same code path signal_service.py
will use in production) ending at a FIXED past timestamp, regenerates
signals, and diffs against the signals produced offline from the stored
parquet (what the backtest used) for the identical bars. Any mismatch means
live and backtest are computing different things — a bug that must be fixed
before going anywhere near real money.
"""
import ccxt
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals
from src.live.signal_service import generate_live_signal

SYMBOL = "ETH/USDT:USDT"
LOCKED_CONFIG = {"adx": 35, "sl": 2.5}

# fixed past timestamp — well within stored history, comfortably before "now"
# so every bar we compare against is fully closed and unambiguous on both sides
AS_OF = pd.Timestamp("2026-08-01 00:00:00", tz="UTC")
AS_OF_MS = int(AS_OF.timestamp() * 1000)

print(f"Replay check as of {AS_OF} ...")

# --- LIVE path: fresh fetch from exchange (public data, no auth needed) ---
exchange = ccxt.binanceusdm({"enableRateLimit": True})
exchange.load_markets()
live_signals = generate_live_signal(exchange, SYMBOL, LOCKED_CONFIG["adx"], LOCKED_CONFIG["sl"], as_of_ms=AS_OF_MS)

# --- BACKTEST path: same functions, but fed from the stored parquet ---
m15_stored = pd.read_parquet("data/raw/ETHUSDT_15m.parquet")
h1_stored = pd.read_parquet("data/raw/ETHUSDT_1h.parquet")
m15_stored = m15_stored[m15_stored["time_utc"] <= AS_OF].reset_index(drop=True)
h1_stored = h1_stored[h1_stored["time_utc"] <= AS_OF].reset_index(drop=True)

features_stored = build_features(m15_stored, h1_stored)
regime_stored = classify_regime(features_stored, adx_threshold=LOCKED_CONFIG["adx"])
backtest_signals = generate_v0_signals(m15_stored, features_stored, regime_stored, sl_atr_mult=LOCKED_CONFIG["sl"])

# --- compare the last N bars where both sides have full warm-up ---
N = 500
live_tail = live_signals.tail(N).reset_index(drop=True)
backtest_tail = backtest_signals[backtest_signals["time_utc"] <= AS_OF].tail(N).reset_index(drop=True)

print(f"Live signals tail: {len(live_tail)} rows, time range {live_tail['time_utc'].min()} -> {live_tail['time_utc'].max()}")
print(f"Backtest signals tail: {len(backtest_tail)} rows, time range {backtest_tail['time_utc'].min()} -> {backtest_tail['time_utc'].max()}")

# align on time_utc explicitly rather than assuming identical row order/length
merged = live_tail.merge(backtest_tail, on="time_utc", suffixes=("_live", "_backtest"), how="inner")
print(f"\nMatched on time_utc: {len(merged)} rows")

mismatches = merged[merged["action_live"] != merged["action_backtest"]]
print(f"Action mismatches: {len(mismatches)}")
if len(mismatches) > 0:
    print(mismatches[["time_utc", "action_live", "action_backtest", "close_live", "close_backtest"]].to_string())

price_diff = (merged["close_live"] - merged["close_backtest"]).abs()
print(f"Max close price diff (live fetch vs stored parquet): {price_diff.max()}")

trade_rows = merged[merged["action_live"] != "NO_TRADE"]
if len(trade_rows) > 0:
    sl_diff = (trade_rows["sl_price_live"] - trade_rows["sl_price_backtest"]).abs()
    tp_diff = (trade_rows["tp_price_live"] - trade_rows["tp_price_backtest"]).abs()
    print(f"Trade signals in window: {len(trade_rows)}")
    print(f"Max SL price diff: {sl_diff.max()}, Max TP price diff: {tp_diff.max()}")
    assert sl_diff.max() < 0.01 and tp_diff.max() < 0.01, "SL/TP prices diverge between live and backtest paths!"

assert len(mismatches) == 0, "Live signal generation does NOT match backtest — see §16 acceptance criteria."
assert price_diff.max() < 0.01, "Live-fetched close prices differ from stored parquet — data source mismatch."

print("\nPASS: live signal generation matches backtest 100% on the compared window.")
