"""Backfill regime_states via src/regime/engine.py::classify_regime_v2 — satisfies
the P4 DoD "regime + confidence + features + timestamp เขียนลง DB ทุกแท่ง"
(docs/XAU_ARCHITECTURE_AUDIT.md §10) against real XAU M15 data.

This does NOT touch the live ETH/XRP pipeline or its DB rows (data/trading.db's
`signals` table already has its own, unrelated `regime` column written by the
locked src/regime/rules.py::classify_regime — see src/data/db.py's regime_states
comment). Point --db-path at a fresh/dedicated DB file for XAU backfills so this
never collides with the live crypto DB.

Kept as a CLI rather than a pytest test: it needs the real multi-GB parquet files
(same rationale as scripts/validate_gold_data.py) and does real DB I/O.

Usage (PYTHONPATH=. required, same as the other scripts/run_gold_r*.py):
    PYTHONPATH=. python scripts/backfill_regime_states.py [--start 2022-01-01] [--end 2024-01-01] [--db-path data/xau_regime.db]
"""
import argparse
import sys

from src.backtest.gold_harness import load_spec, load_gold_data
from src.data.db import init_db
from src.features.engine import build_features
from src.live.logging_store import log_regime_states
from src.regime.engine import classify_regime_v2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--db-path", default="data/xau_regime.db")
    args = parser.parse_args()

    spec = load_spec()
    m15, h1, _m1 = load_gold_data(spec, start=args.start, end=args.end)
    print(f"[regime] loaded {args.symbol}: m15={len(m15):,} h1={len(h1):,}")

    features = build_features(m15, h1)
    regime_df = classify_regime_v2(features)

    engine = init_db(args.db_path)
    n = log_regime_states(engine, args.symbol, "M15", regime_df)
    print(f"[regime] wrote {n:,} rows to {args.db_path} (table regime_states)")

    counts = regime_df["regime"].value_counts()
    print("\nregime distribution:")
    for cls, cnt in counts.items():
        print(f"  {cls:22s} {cnt:>8,}  ({cnt / len(regime_df):.1%})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
