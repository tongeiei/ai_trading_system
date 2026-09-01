"""R2 — ORB + Fib pullback on XAU/USD spot, via the gold harness.

  PYTHONPATH=. .venv/bin/python scripts/run_gold_r2_orb_pullback.py         # last ~3y
  PYTHONPATH=. .venv/bin/python scripts/run_gold_r2_orb_pullback.py --full  # 20y + sweep

First-look single-config WFO, optimistic costs — same caveats as R1
(docs/research/XAU_REDDIT_SCOUT.md).
"""
import sys

from src.backtest.gold_harness import (
    load_spec, load_gold_data, build_features,
    label_all_signals, apply_gold_costs, evaluate, walk_forward, run_gold_backtest,
)
from src.strategy.gold_orb_pullback import generate_orb_pullback_signals


def make_signal_fn(**params):
    def signal_fn(m15, h1, features):
        return generate_orb_pullback_signals(m15, **params)
    return signal_fn


def main() -> None:
    full = "--full" in sys.argv
    start = None if full else "2022-08-01"
    spec = load_spec()
    print(f"cost (bps/side): spread={spec['costs']['spread_bps_per_side']} "
          f"slip={spec['costs']['slippage_bps_per_side']} comm={spec['costs']['commission_bps_per_side']} (no funding)")

    print("\n########## R2 ORB+pullback baseline (OR=30m, fib=0.5, TP=2R, both) ##########")
    run_gold_backtest(make_signal_fn(or_minutes=30, fib_ratio=0.5, tp_r_mult=2.0), spec=spec, start=start)

    if not full:
        print("\n[R2] baseline done. Re-run with --full for the 20y sweep.")
        return

    print("\n########## R2 sweep (full history) ##########")
    m15, h1, m1 = load_gold_data(spec, None, None)
    _ = build_features(m15, h1)  # not used by ORB but keeps the pipe identical
    print(f"{'or':>3} {'fib':>5} {'tp':>4} {'dir':>5} | {'n':>4} {'win%':>6} {'meanR':>7} "
          f"{'PF':>6} {'totR':>8} {'folds+':>7} GATE")
    for or_minutes in (30, 60):
        for fib in (0.382, 0.5, 0.618):
            for tp in (1.5, 2.0):
                for direction in ("both", "long"):
                    sig = generate_orb_pullback_signals(
                        m15, or_minutes=or_minutes, fib_ratio=fib, tp_r_mult=tp, direction=direction)
                    live = sig[sig["action"] != "NO_TRADE"] if not sig.empty else sig
                    if live.empty:
                        print(f"{or_minutes:>3} {fib:>5} {tp:>4} {direction:>5} | (no trades)")
                        continue
                    costed = apply_gold_costs(label_all_signals(live, m1), spec)
                    e, w = evaluate(costed), walk_forward(costed, spec)
                    print(f"{or_minutes:>3} {fib:>5} {tp:>4} {direction:>5} | {e['n']:>4} "
                          f"{e['win_rate']*100:>5.1f} {e['mean_r']:>7.3f} {e['profit_factor']:>6.2f} "
                          f"{e['total_r']:>8.1f} {w['frac_folds_positive']*100:>6.0f}% "
                          f"{'PASS' if w['gate_pass'] else 'fail'}")


if __name__ == "__main__":
    main()
