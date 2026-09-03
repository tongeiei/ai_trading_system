"""Phase 0 of docs/research/PLAN_CUSTOM.md — opportunity funnel diagnosis for V0.

Read-only research script. Does NOT import or modify src/strategy/v0_rules.py's
live thresholds — it re-derives the same funnel stages from features/regime
directly so the production strategy file stays untouched, per PLAN_CUSTOM's
"do not modify the live strategy" rule.

Splits data into a RESEARCH POOL (everything before SACRED_HOLDOUT_START) and
a SACRED HOLDOUT (last ~8 weeks, the only truly-unseen window left after the
prior screening + 12-fold WFO + ATR-filter experiments already consumed
2023-08 through 2026-06 — see docs/FINDINGS.md). Only the research pool is
used here; the holdout is loaded but never inspected beyond its date range,
to keep it clean for final variant validation later.

Usage: .venv/bin/python scripts/research_funnel_diagnosis.py
"""
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime

# --- locked live config (read-only reference values, not imported from
# production code, so this script can't accidentally drift from or mutate it) ---
LIVE_ADX_THRESHOLD = 35.0
LIVE_TREND_STRENGTH_THRESHOLD = 0.5

SACRED_HOLDOUT_START = pd.Timestamp("2026-07-01", tz="UTC")


def load_eth():
    m15 = pd.read_parquet("data/raw/ETHUSDT_15m.parquet")
    h1 = pd.read_parquet("data/raw/ETHUSDT_1h.parquet")
    return m15, h1


def main():
    m15, h1 = load_eth()
    print(f"Full data range: {m15['time_utc'].min()} -> {m15['time_utc'].max()} ({len(m15)} M15 bars)")
    print(f"SACRED_HOLDOUT_START = {SACRED_HOLDOUT_START} — excluded from this diagnosis")

    pool_m15 = m15[m15["time_utc"] < SACRED_HOLDOUT_START].reset_index(drop=True)
    pool_h1 = h1[h1["time_utc"] < SACRED_HOLDOUT_START].reset_index(drop=True)
    holdout_bars = len(m15) - len(pool_m15)
    print(f"Research pool: {len(pool_m15)} M15 bars ({pool_m15['time_utc'].min()} -> {pool_m15['time_utc'].max()})")
    print(f"Sacred holdout (untouched): {holdout_bars} M15 bars\n")

    features = build_features(pool_m15, pool_h1)
    regime = classify_regime(features, adx_threshold=LIVE_ADX_THRESHOLD,
                              trend_strength_threshold=LIVE_TREND_STRENGTH_THRESHOLD)

    close = pool_m15["close"].reset_index(drop=True)
    dist_ema20 = features["f01_dist_ema20_atr"].reset_index(drop=True)
    prev_dist_ema20 = dist_ema20.shift(1)
    h1_trend = features["f03_h1_trend_atr"].reset_index(drop=True)
    atr_pct = features["f08_atr_percentile"].reset_index(drop=True)
    body_ratio = features["f10_candle_body_ratio"].reset_index(drop=True)
    regime = regime.reset_index(drop=True)

    warmed_up = atr_pct.notna()

    stage_all = warmed_up
    stage_trend_regime = stage_all & (regime == "TREND")

    long_dir = stage_trend_regime & (h1_trend > 0)
    short_dir = stage_trend_regime & (h1_trend < 0)
    stage_valid_direction = long_dir | short_dir

    long_pullback = long_dir & (prev_dist_ema20 <= 0) & (dist_ema20 > 0)
    short_pullback = short_dir & (prev_dist_ema20 >= 0) & (dist_ema20 < 0)
    stage_pullback_candidate = long_pullback | short_pullback

    # live defaults: atr_pct_min=0.0, atr_pct_max=1.0 (no-op), min_body_ratio=0.0 (no-op)
    vol_ok = (atr_pct >= 0.0) & (atr_pct <= 1.0)
    body_ok = body_ratio >= 0.0
    stage_atr_filter = stage_pullback_candidate & vol_ok
    stage_quality_filter = stage_atr_filter & body_ok

    # EV gate is a live-only historical-stat check (src/live/ev_estimate.py),
    # not reproducible bar-by-bar from backtest features alone — omitted here,
    # noted as a separate funnel stage in the report.

    def pct(mask):
        return 100 * mask.sum() / stage_all.sum()

    rows = [
        ("M15 bars (warmed up)", stage_all.sum(), 100.0),
        ("-> H1 TREND regime bars", stage_trend_regime.sum(), pct(stage_trend_regime)),
        ("-> valid H1 direction (bullish or bearish)", stage_valid_direction.sum(), pct(stage_valid_direction)),
        ("-> EMA20 pullback candidate", stage_pullback_candidate.sum(), pct(stage_pullback_candidate)),
        ("-> ATR filter passed (no-op at live defaults)", stage_atr_filter.sum(), pct(stage_atr_filter)),
        ("-> candle-quality filter passed (no-op at live defaults)", stage_quality_filter.sum(), pct(stage_quality_filter)),
    ]

    print(f"{'Stage':<55} {'Bars':>8} {'% of warmed-up bars':>20}")
    for name, n, p in rows:
        print(f"{name:<55} {n:>8} {p:>19.3f}%")

    print(f"\nLONG candidates at pullback stage: {long_pullback.sum()}")
    print(f"SHORT candidates at pullback stage: {short_pullback.sum()}")

    n_years = (pool_m15["time_utc"].max() - pool_m15["time_utc"].min()).days / 365.25
    print(f"\nResearch pool span: {n_years:.2f} years")
    print(f"Eligible trades/year (pre-EV-gate): {stage_quality_filter.sum() / n_years:.1f}")

    # attrition ratios between consecutive stages, to see where the biggest single drop is
    print("\n--- stage-to-stage attrition (biggest drop = bottleneck) ---")
    stages = [stage_all, stage_trend_regime, stage_valid_direction, stage_pullback_candidate, stage_atr_filter, stage_quality_filter]
    names = ["all", "TREND regime", "valid direction", "pullback candidate", "ATR filter", "quality filter"]
    for i in range(1, len(stages)):
        prev_n, cur_n = stages[i - 1].sum(), stages[i].sum()
        drop_pct = 100 * (1 - cur_n / prev_n) if prev_n else float("nan")
        print(f"{names[i-1]:>20} -> {names[i]:<20} kept {cur_n:>6}/{prev_n:<6} (dropped {drop_pct:.1f}%)")


if __name__ == "__main__":
    main()
