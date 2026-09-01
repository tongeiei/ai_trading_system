"""R5 — DXY regime filter on XAU/USD spot, via the gold harness.

  PYTHONPATH=. .venv/bin/python -u scripts/run_gold_r5_dxy_filter.py          # 3y smoke
  PYTHONPATH=. .venv/bin/python -u scripts/run_gold_r5_dxy_filter.py --full   # 20y DEV grid
  PYTHONPATH=. .venv/bin/python -u scripts/run_gold_r5_dxy_filter.py --holdout CFG  # holdout, ONE touch
  PYTHONPATH=. .venv/bin/python -u scripts/run_gold_r5_dxy_filter.py --coststress CFG START END

See src/strategy/gold_r5_dxy_filter.py module docstring for the pre-registered
rule spec. Grid (DEV, 2006-2018 only): ma_len in {20,50,100,200} x mode in
{regime_directional, regime_long_filter, regime_short_filter}, plus
always_long / always_short baselines (mode-invariant to ma_len) and one
inverted_directional asymmetry check at ma_len=50.
"""
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]

from src.backtest.gold_harness import (
    load_spec, load_gold_data, build_features,
    label_all_signals, apply_gold_costs, evaluate, walk_forward, run_gold_backtest,
)
from src.strategy.gold_r5_dxy_filter import generate_r5_signals

DEV_START, DEV_END = "2006-01-01", "2018-12-31"
HOLDOUT_START, HOLDOUT_END = "2019-01-01", None

MA_GRID = (20, 50, 100, 200)
MODE_GRID = ("regime_directional", "regime_long_filter", "regime_short_filter")
BASELINE_MODES = ("always_long", "always_short")


def load_dxy() -> pd.DataFrame:
    return pd.read_parquet(REPO_ROOT / "data/raw/DXY_daily.parquet")


def make_signal_fn(dxy, **params):
    def signal_fn(m15, h1, features):
        return generate_r5_signals(m15, dxy, **params)
    return signal_fn


def run_grid(m15, m1, dxy, spec, tag=""):
    print(f"\n{'ma':>4} {'mode':>20} | {'n':>5} {'win%':>6} {'meanR':>8} "
          f"{'PF':>6} {'totR':>8} {'folds':>5} {'folds+':>7} GATE")
    rows = []
    for mode in BASELINE_MODES:
        sig = generate_r5_signals(m15, dxy, ma_len=50, mode=mode)
        live = sig[sig["action"] != "NO_TRADE"]
        if live.empty:
            print(f"{'--':>4} {mode:>20} | (no trades)")
            continue
        costed = apply_gold_costs(label_all_signals(live, m1), spec)
        e, w = evaluate(costed), walk_forward(costed, spec)
        rows.append((mode, None, e, w))
        print(f"{'--':>4} {mode:>20} | {e['n']:>5} {e['win_rate']*100:>5.1f} {e['mean_r']:>8.4f} "
              f"{e['profit_factor']:>6.2f} {e['total_r']:>8.1f} {w['n_folds']:>5} "
              f"{w['frac_folds_positive']*100:>6.0f}% {'PASS' if w['gate_pass'] else 'fail'}")

    for ma in MA_GRID:
        for mode in MODE_GRID:
            sig = generate_r5_signals(m15, dxy, ma_len=ma, mode=mode)
            live = sig[sig["action"] != "NO_TRADE"]
            if live.empty:
                print(f"{ma:>4} {mode:>20} | (no trades)")
                continue
            costed = apply_gold_costs(label_all_signals(live, m1), spec)
            e, w = evaluate(costed), walk_forward(costed, spec)
            rows.append((mode, ma, e, w))
            print(f"{ma:>4} {mode:>20} | {e['n']:>5} {e['win_rate']*100:>5.1f} {e['mean_r']:>8.4f} "
                  f"{e['profit_factor']:>6.2f} {e['total_r']:>8.1f} {w['n_folds']:>5} "
                  f"{w['frac_folds_positive']*100:>6.0f}% {'PASS' if w['gate_pass'] else 'fail'}")

    # asymmetry sanity check
    sig = generate_r5_signals(m15, dxy, ma_len=50, mode="inverted_directional")
    live = sig[sig["action"] != "NO_TRADE"]
    if not live.empty:
        costed = apply_gold_costs(label_all_signals(live, m1), spec)
        e, w = evaluate(costed), walk_forward(costed, spec)
        print(f"{50:>4} {'inverted_directional':>20} | {e['n']:>5} {e['win_rate']*100:>5.1f} "
              f"{e['mean_r']:>8.4f} {e['profit_factor']:>6.2f} {e['total_r']:>8.1f} {w['n_folds']:>5} "
              f"{w['frac_folds_positive']*100:>6.0f}% {'PASS' if w['gate_pass'] else 'fail'}")
    return rows


def main() -> None:
    full = "--full" in sys.argv
    spec = load_spec()
    dxy = load_dxy()
    print(f"cost (bps/side): spread={spec['costs']['spread_bps_per_side']} "
          f"slip={spec['costs']['slippage_bps_per_side']} comm={spec['costs']['commission_bps_per_side']} (no funding)")
    print(f"DXY daily rows={len(dxy)} range={dxy['time_utc'].min()} .. {dxy['time_utc'].max()}")

    start = None if full else "2022-08-01"
    end = None

    base_cfg = dict(ma_len=50, mode="regime_directional")
    print(f"\n########## R5 smoke {base_cfg} (start={start}) ##########")
    m15, h1, m1 = load_gold_data(spec, start, end)
    _ = build_features(m15, h1)
    run_gold_backtest(make_signal_fn(dxy, **base_cfg), spec=spec, start=start, end=end)

    if not full:
        print("\n[R5] smoke done. Re-run with --full for the DEV grid (2006-2018).")
        return

    print(f"\n########## R5 DEV grid (sacred DEV window {DEV_START}..{DEV_END}) ##########")
    m15, h1, m1 = load_gold_data(spec, DEV_START, DEV_END)
    _ = build_features(m15, h1)
    run_grid(m15, m1, dxy, spec, tag="DEV")


if __name__ == "__main__":
    main()
