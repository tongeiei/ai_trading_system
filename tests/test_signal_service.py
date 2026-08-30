from src.live.signal_service import fetch_recent_ohlcv


class FakeExchange:
    """Minimal ccxt-like stub: one fetch_ohlcv call returns all bars at once."""

    def __init__(self, bars):
        self.bars = bars  # list of [ts_ms, o, h, l, c, v]
        self.rateLimit = 0

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        batch = [b for b in self.bars if b[0] >= since]
        return batch[:limit]

    def sleep(self, ms):
        pass


def test_forming_bar_is_excluded_even_though_its_open_time_is_within_range():
    # Regression test for the 2026-08-30 bug: a cycle firing at 14:15:30 (bar
    # buffer) must not see the 14:15 bar (open=14:15, not yet closed) as the
    # last row — only the fully-closed 14:00 bar should be last. An open-time
    # filter (b[0] <= end_ms) let the forming bar through; the fix filters on
    # close time (b[0] + ms_per_candle <= end_ms).
    ms_per_candle = 900_000
    base = 1_756_000_000_000  # arbitrary aligned epoch ms
    bars = [
        [base - ms_per_candle, 1, 1, 1, 1, 1],  # 13:45 bar, closed
        [base, 1, 1, 1, 1, 1],  # 14:00 bar, closed
        [base + ms_per_candle, 1, 1, 1, 1, 1],  # 14:15 bar, still forming
    ]
    exchange = FakeExchange(bars)
    end_ms = base + ms_per_candle + 30_000  # cycle fires 30s into the 14:15 bar

    df = fetch_recent_ohlcv(exchange, "ETH/USDT:USDT", "15m", warmup_days=1, end_ms=end_ms)

    assert df["ts_ms" if "ts_ms" in df.columns else "time_utc"].iloc[-1] is not None
    last_ms = int(df["time_utc"].iloc[-1].value // 1_000_000)
    assert last_ms == base, "last row must be the closed 14:00 bar, not the forming 14:15 bar"
    assert len(df) == 2
