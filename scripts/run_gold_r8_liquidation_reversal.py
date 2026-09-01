"""R8 — Post-liquidation reversal on XAU/USD spot, via the gold harness.

  PYTHONPATH=. .venv/bin/python -u scripts/run_gold_r8_liquidation_reversal.py         # 3y smoke
  PYTHONPATH=. .venv/bin/python -u scripts/run_gold_r8_liquidation_reversal.py --full   # 20y baseline + sweep

docs/research/R8_PLAN.md §4 grid + §6a naive-baseline comparison.
"""
import sys

from src.backtest.gold_harness import (
    load_spec, load_gold_data, build_features,
    label_all_signals, apply_gold_costs, evaluate, walk_forward, run_gold_backtest,
)
from src.strategy.gold_r8_liquidation_reversal import generate_r8_signals


def make_signal_fn(**params):
    def signal_fn(m15, h1, features):
        return generate_r8_signals(m15, **params)
    return signal_fn


def main() -> None:
    full = "--full" in sys.argv
    start = None if full else "2022-08-01"
    spec = load_spec()
    print(f"cost (bps/side): spread={spec['costs']['spread_bps_per_side']} "
          f"slip={spec['costs']['slippage_bps_per_side']} comm={spec['costs']['commission_bps_per_side']} (no funding)")

    base_cfg = dict(k_capit=2.5, tp_r_mult=1.5, M=3, direction="both")
    print(f"\n########## R8 baseline {base_cfg} ##########")
    run_gold_backtest(make_signal_fn(**base_cfg), spec=spec, start=start)

    print(f"\n########## R8 naive baseline (no confirm wait) {base_cfg} ##########")
    run_gold_backtest(make_signal_fn(baseline=True, **base_cfg), spec=spec, start=start)

    if not full:
        print("\n[R8] smoke done. Re-run with --full for the 20y sweep.")
        return

    print("\n########## R8 sweep (full history) ##########")
    m15, h1, m1 = load_gold_data(spec, None, None)
    _ = build_features(m15, h1)
    print(f"{'k':>4} {'tp':>4} {'M':>2} {'dir':>5} | {'n':>5} {'win%':>6} {'meanR':>8} "
          f"{'PF':>6} {'totR':>8} {'folds+':>7} GATE")
    for k in (2.0, 2.5, 3.0):
        for tp in (1.0, 1.5, 2.0):
            for M in (1, 3):
                for direction in ("both", "long"):
                    sig = generate_r8_signals(m15, k_capit=k, tp_r_mult=tp, M=M, direction=direction)
                    live = sig[sig["action"] != "NO_TRADE"] if not sig.empty else sig
                    if live.empty:
                        print(f"{k:>4} {tp:>4} {M:>2} {direction:>5} | (no trades)")
                        continue
                    costed = apply_gold_costs(label_all_signals(live, m1), spec)
                    e, w = evaluate(costed), walk_forward(costed, spec)
                    print(f"{k:>4} {tp:>4} {M:>2} {direction:>5} | {e['n']:>5} "
                          f"{e['win_rate']*100:>5.1f} {e['mean_r']:>8.4f} {e['profit_factor']:>6.2f} "
                          f"{e['total_r']:>8.1f} {w['frac_folds_positive']*100:>6.0f}% "
                          f"{'PASS' if w['gate_pass'] else 'fail'}")


if __name__ == "__main__":
    main()
