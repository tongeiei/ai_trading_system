"""Shadow-mode scorecard logging -- docs/XAU_ARCHITECTURE_AUDIT.md §16.6 item 2:
"log scorecard ทุก setup แต่ยังไม่ให้คุม risk tier" (log every setup's scorecard,
but it does not control risk tier yet).

Reuses the exact same scoring pipeline scripts/bucket_test_scorecard.py already
validated (score_all_strategies) -- this script's only job is to persist those
scores + gate decisions to the `scorecard_log` DB table (src/data/db.py) for
future tracking, NOT to compute anything differently.

§17 records the bucket test result as weak/mixed (real but tiny, inconsistent
per-strategy, no profitable bucket) -- this logging is explicitly NOT a signal
that the scorecard is validated for controlling risk. gate()'s decision/risk_pct
are logged for observability only; nothing reads them to size a real order.

veto/veto_reason/thesis are logged as NULL -- src/ai/analyst.py (the LLM layer)
is deliberately not called here, to avoid spending real API budget validating a
scorecard that hasn't earned it (per the same §17 caveat).

Kept as a CLI rather than a pytest test: needs real multi-GB parquet data and
writes to a real DB file, same rationale as the other scripts/*.py in this family.

Usage (PYTHONPATH=. required, same as the other scripts/run_gold_r*.py):
    PYTHONPATH=. python scripts/shadow_log_scorecard.py [--start 2015-01-01] [--end 2024-01-01] [--db-path data/xau_shadow.db]
"""
import argparse
import sys

from src.ai.scorecard import gate
from src.backtest.gold_harness import load_gold_data, load_spec
from src.data.db import init_db
from src.live.logging_store import log_scorecard_batch
from scripts.bucket_test_scorecard import score_all_strategies


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--db-path", default="data/xau_shadow.db")
    args = parser.parse_args()

    spec = load_spec()
    m15, h1, m1 = load_gold_data(spec, start=args.start, end=args.end)
    print(f"[shadow_log] loaded {args.symbol}: m15={len(m15):,} h1={len(h1):,} m1={len(m1):,}")

    pooled = score_all_strategies(m15, h1, m1, spec)
    if pooled.empty:
        print("[shadow_log] no trades from any strategy -- nothing to log")
        return 1

    gate_results = pooled.apply(
        lambda row: gate(
            _row_to_scorecard(row)
        ),
        axis=1,
    )
    pooled["decision"] = [g.decision for g in gate_results]
    pooled["risk_pct"] = [g.risk_pct for g in gate_results]

    engine = init_db(args.db_path)
    n = log_scorecard_batch(engine, args.symbol, "M15", pooled)
    print(f"[shadow_log] wrote {n:,} rows to {args.db_path} (table scorecard_log)")

    decision_counts = pooled["decision"].value_counts()
    print("\ndecision distribution:")
    for decision, count in decision_counts.items():
        print(f"  {decision:14s} {count:>8,}  ({count / len(pooled):.1%})")

    return 0


def _row_to_scorecard(row):
    from src.ai.scorecard import Scorecard
    return Scorecard(
        trend=row.trend, structure=row.structure, momentum=row.momentum,
        volatility=row.volatility, session=row.session, risk=row.risk,
        final_score=row.final_score, weakest_link_block=bool(row.weakest_link_block),
    )


if __name__ == "__main__":
    sys.exit(main())
