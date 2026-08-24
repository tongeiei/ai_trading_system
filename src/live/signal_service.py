"""Live signal generation — PROJECT_PLAN.md §12.3/§16.

Uses the EXACT same feature/regime/strategy functions as the backtest
(features.engine, regime.rules, strategy.v0_rules) — the only thing that
differs between backtest and live is WHERE the OHLCV data comes from
(stored parquet vs a fresh exchange fetch). If those two paths ever produce
different signals for the same bars, that's a live/backtest divergence bug,
which is exactly what §16's replay check exists to catch.
"""
import ccxt
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals

# 60 days of M15 warm-up for the ATR percentile rolling window (§4.2 f08),
# plus buffer, plus H1 needs ~200 bars for EMA200 warm-up.
M15_WARMUP_DAYS = 65
H1_WARMUP_DAYS = 20


def fetch_recent_ohlcv(exchange: ccxt.Exchange, symbol: str, timeframe: str, warmup_days: int, end_ms: int | None = None) -> pd.DataFrame:
    """Fetches OHLCV ending at end_ms (or now if None). Public endpoint, no auth needed."""
    ms_per_candle = {"15m": 900_000, "1h": 3_600_000}[timeframe]
    end_ms = end_ms if end_ms is not None else exchange.milliseconds()
    since_ms = end_ms - warmup_days * 24 * 3_600_000

    all_rows = []
    cursor = since_ms
    while cursor < end_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=1500)
        if not batch:
            break
        batch = [b for b in batch if b[0] <= end_ms]
        all_rows.extend(batch)
        last_ts = batch[-1][0] if batch else cursor
        if last_ts <= cursor:
            break
        cursor = last_ts + ms_per_candle
        exchange.sleep(exchange.rateLimit)

    df = pd.DataFrame(all_rows, columns=["ts_ms", "open", "high", "low", "close", "volume"])
    df["time_utc"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    return df.drop(columns=["ts_ms"]).drop_duplicates(subset="time_utc").sort_values("time_utc").reset_index(drop=True)


def generate_live_signal(exchange: ccxt.Exchange, symbol: str, adx_threshold: float, sl_atr_mult: float,
                          as_of_ms: int | None = None) -> pd.DataFrame:
    """Returns the full signal dataframe (same shape as backtest) computed
    from freshly-fetched exchange data, up to (and including) the last fully
    closed bar as of as_of_ms."""
    m15 = fetch_recent_ohlcv(exchange, symbol, "15m", M15_WARMUP_DAYS, as_of_ms)
    h1 = fetch_recent_ohlcv(exchange, symbol, "1h", H1_WARMUP_DAYS + M15_WARMUP_DAYS, as_of_ms)

    features = build_features(m15, h1)
    regime = classify_regime(features, adx_threshold=adx_threshold)
    signals = generate_v0_signals(m15, features, regime, sl_atr_mult=sl_atr_mult)
    return signals
