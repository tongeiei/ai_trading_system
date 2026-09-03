"""Bucket test for src/ai/scorecard.py -- docs/XAU_ARCHITECTURE_AUDIT.md §16.6
item 1, the kill switch that must run BEFORE building the rest of P6 (shadow-mode
logging, DB wiring, the Macro A/B). Reuses labeled trades the 4 falsified gold
strategies with a locked FROZEN_CFG already leave behind (net_r_multiple per
trade, no LLM call, no new backtest claim) and asks: does the scorecard's Final
Score actually correlate with realized R? If mean R does not climb with score,
the scorecard is decoration and this reports that plainly -- it does not try to
make the result look better.

Covers R11/R14/R15/R17 only (not all 8 falsified strategies) -- these are the
ones with a single already-locked FROZEN_CFG at module level in their own
scripts/run_gold_r*.py, reused verbatim here rather than re-derived. See
docs/XAU_ARCHITECTURE_AUDIT.md §17 for why R1/R2/R5/R8 are out of scope for this
pass.

Kept as a CLI rather than a pytest test: needs the real multi-GB parquet files
and real backtest time, same rationale as scripts/validate_gold_data.py before it.

Usage (PYTHONPATH=. required, same as the other scripts/run_gold_r*.py):
    PYTHONPATH=. python scripts/bucket_test_scorecard.py [--start 2006-01-01] [--end 2018-12-31]
"""
import argparse
import sys

import numpy as np
import pandas as pd

from src.ai.scorecard import compute_scorecard_batch
from src.backtest.gold_harness import apply_gold_costs, load_gold_data, load_spec
from src.labeling.triple_barrier import label_all_signals
from src.strategy.gold_r11_wick_fill import generate_r11_signals
from src.strategy.gold_r14_fake_zone import generate_r14_signals
from src.strategy.gold_r15_choch import generate_r15_signals
from src.strategy.gold_r17_fvg import generate_r17_signals

# Reused verbatim from each strategy's own scripts/run_gold_r*.py -- NOT
# re-derived here, so this pass can't accidentally misconfigure an entry rule.
STRATEGIES = {
    "R11_wick_fill": (generate_r11_signals, dict(k_wick=1.5, body_frac=0.5, tp_mode="wick_fill", direction="both")),
    "R14_fake_zone": (generate_r14_signals, dict(w=3, b_break=0.5, N=3, tp_r_mult=1.5, direction="both")),
    "R15_choch": (generate_r15_signals, dict(w=5, k_range=2.0, tp_r_mult=1.5, direction="both")),
    "R17_fvg": (generate_r17_signals, dict(k_gap=0.5, N=10, tp_r_mult=1.5, direction="both")),
}


def _bucket_report(df: pd.DataFrame, score_col: str, r_col: str, label: str) -> None:
    print(f"\n--- {label} ---")
    print(f"n={len(df)}  mean_final_score={df[score_col].mean():.1f}  mean_R={df[r_col].mean():.4f}")

    bands = pd.cut(df[score_col], bins=[-1, 60, 75, 101], labels=["<60 NO_TRADE", "60-75 small", ">75 normal"])
    band_stats = df.groupby(bands, observed=True)[r_col].agg(["count", "mean", "median"])
    print("\n§16.3 gating bands:")
    print(band_stats.to_string())

    deciles = pd.qcut(df[score_col], q=10, duplicates="drop")
    decile_stats = df.groupby(deciles, observed=True)[r_col].agg(["count", "mean", "median"])
    print("\ndeciles (finer view):")
    print(decile_stats.to_string())

    monotonic = band_stats["mean"].is_monotonic_increasing
    print(f"\nmean R monotonic across gating bands: {monotonic}")

    valid = df[[score_col, r_col]].dropna()
    corr = valid[score_col].corr(valid[r_col]) if len(valid) > 2 else float("nan")
    print(f"Pearson corr(final_score, {r_col}) = {corr:.4f}")


def score_all_strategies(m15, h1, m1, spec, verbose: bool = True) -> pd.DataFrame:
    """Runs each of STRATEGIES' locked FROZEN_CFG, labels + costs the trades, and
    scores them with compute_scorecard_batch. Returns the pooled DataFrame (one
    row per trade, with a `strategy` column) -- reused by both this script and
    scripts/shadow_log_scorecard.py so the two never compute the scorecard
    differently for the same trades."""
    all_scored = []
    for name, (signal_fn, cfg) in STRATEGIES.items():
        signals = signal_fn(m15, **cfg)
        if signals.empty:
            if verbose:
                print(f"[bucket_test] {name}: 0 signals, skipping")
            continue
        labeled = label_all_signals(signals, m1)
        costed = apply_gold_costs(labeled, spec)
        scored = compute_scorecard_batch(m15, h1, costed)
        scored["strategy"] = name
        all_scored.append(scored)
        if verbose:
            print(f"[bucket_test] {name}: {len(scored):,} labeled trades")

    if not all_scored:
        return pd.DataFrame()
    return pd.concat(all_scored, ignore_index=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args()

    spec = load_spec()
    m15, h1, m1 = load_gold_data(spec, start=args.start, end=args.end)
    print(f"[bucket_test] loaded XAUUSD: m15={len(m15):,} h1={len(h1):,} m1={len(m1):,}")

    pooled = score_all_strategies(m15, h1, m1, spec)
    if pooled.empty:
        print("[bucket_test] no trades from any strategy -- nothing to test")
        return 1

    for name, group in pooled.groupby("strategy"):
        _bucket_report(group, "final_score", "net_r_multiple", name)

    _bucket_report(pooled, "final_score", "net_r_multiple", "POOLED (all 4 strategies)")

    print("\n=== VERDICT ===")
    bands = pd.cut(pooled["final_score"], bins=[-1, 60, 75, 101], labels=["low", "mid", "high"])
    band_means = pooled.groupby(bands, observed=True)["net_r_multiple"].mean()
    passed = band_means.is_monotonic_increasing
    print(f"mean R monotonic across score bands (pooled): {passed}")
    print(band_means.to_string())
    if passed:
        print("\nScorecard shows the expected ordering on this sample -- proceed to")
        print("shadow-mode logging per §16.6 item 2.")
    else:
        print("\nScorecard does NOT show the expected ordering on this sample -- per")
        print("§16.6's own framing, this is a kill signal, not something to re-tune")
        print("until it passes. Document as-is in docs/XAU_ARCHITECTURE_AUDIT.md §17.")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
