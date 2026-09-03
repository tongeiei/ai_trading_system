"""Run the data-quality validation layer (src/data/validation.py) against the
real XAU/USD parquet files on disk — satisfies the P2 DoD "validation test
passes" (docs/XAU_ARCHITECTURE_AUDIT.md §10) against real data.

Kept as a CLI rather than a pytest test: it needs the real multi-GB parquet
files (not present in a fresh checkout until scripts/fetch_xau_dukascopy.py
has been run for all 5 timeframes) and real I/O time, so it must not be part
of the fast `pytest tests -q` regression gate.

Usage (PYTHONPATH=. required, same as the other scripts/run_gold_r*.py):
    PYTHONPATH=. python scripts/validate_gold_data.py
"""
import sys

import pandas as pd

from src.backtest.gold_harness import load_spec, load_gold_data_all
from src.data.validation import validate_timeframe

# gold_spec.yaml's data keys ("m1"/"m5"/.../"h4") vs validation.TIMEFRAME_STEPS'
# naming ("1m"/"5m"/.../"4h") — same mapping used in src/data/mt5_feed.py.
VALIDATION_TIMEFRAME = {"m1": "1m", "m5": "5m", "m15": "15m", "h1": "1h", "h4": "4h"}

# (native timeframe, resample-from timeframe, pandas resample rule) — only
# pairs where a finer-grained series exists to resample from and cross-check.
RECONCILE_AGAINST = {
    "m5": ("m1", "5min"),
    "h4": ("h1", "4h"),
}


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    ohlc = (
        df.set_index("time_utc")
        .resample(rule)
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open"])
        .reset_index()
    )
    return ohlc


def main() -> int:
    spec = load_spec()
    frames = load_gold_data_all(spec)

    all_ok = True
    for timeframe, df in frames.items():
        secondary = None
        if timeframe in RECONCILE_AGAINST:
            base_tf, rule = RECONCILE_AGAINST[timeframe]
            if base_tf in frames:
                secondary = _resample(frames[base_tf], rule)

        report = validate_timeframe(df, VALIDATION_TIMEFRAME[timeframe], secondary=secondary)
        print(report.summary())
        for issue in report.issues:
            if issue.severity == "error":
                print(f"  ERROR [{issue.kind}] {issue.time_utc}: {issue.detail}")
        all_ok = all_ok and report.ok

    if all_ok:
        print("\nALL TIMEFRAMES OK")
        return 0
    print("\nVALIDATION FAILED — see ERROR lines above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
