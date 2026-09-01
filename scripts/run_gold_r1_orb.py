"""R1 — Opening Range Breakout on XAU/USD spot, via the gold harness.

  PYTHONPATH=. .venv/bin/python scripts/run_gold_r1_orb.py            # last ~3y
  PYTHONPATH=. .venv/bin/python scripts/run_gold_r1_orb.py --full     # 20y + sweep

This is a FIRST-LOOK single-config walk-forward, not a promotion decision:
no per-fold refit yet, and costs are the optimistic assumptions in
config/gold_spec.yaml. Read the caveats in docs/research/XAU_REDDIT_SCOUT.md.
"""
import sys

from src.backtest.gold_harness import load_spec, load_gold_data, run_gold_backtest
from src.backtest.gold_harness import build_features, label_all_signals, apply_gold_costs
from src.backtest.gold_harness import evaluate, walk_forward
from src.strategy.gold_orb import generate_orb_signals


def make_signal_fn(**params):
    def signal_fn(m15, h1, features):
        return generate_orb_signals(m15, **params)
    return signal_fn


def main() -> None:
    full = "--full" in sys.argv
    start = None if full else "2022-08-01"
    spec = load_spec()
    print(f"cost (bps/side): spread={spec['costs']['spread_bps_per_side']} "
          f"slip={spec['costs']['slippage_bps_per_side']} comm={spec['costs']['commission_bps_per_side']} (no funding)")

    print("\n########## R1 ORB baseline (OR=30m, TP=2R, both dirs) ##########")
    base = run_gold_backtest(make_signal_fn(or_minutes=30, tp_r_mult=2.0), spec=spec, start=start)

    if not full:
        print("\n[R1] baseline done. Re-run with --full for the 20y sweep.")
        return

    # --- small pre-registered sweep (report all, promote none without holdout) ---
    print("\n########## R1 ORB sweep (full history) ##########")
    m15, h1, m1 = load_gold_data(spec, start, None)
    features = build_features(m15, h1)
    print(f"{'or_min':>6} {'tp_R':>5} {'dir':>5} | {'n':>5} {'win%':>6} {'meanR':>7} "
          f"{'PF':>6} {'totR':>8} {'p':>6} {'folds+':>7} GATE")
    for or_minutes in (15, 30, 60):
        for tp in (1.0, 1.5, 2.0):
            for direction in ("both", "long"):
                sig = generate_orb_signals(m15, or_minutes=or_minutes, tp_r_mult=tp, direction=direction)
                live = sig[sig["action"] != "NO_TRADE"]
                if live.empty:
                    continue
                costed = apply_gold_costs(label_all_signals(live, m1), spec)
                e = evaluate(costed)
                w = walk_forward(costed, spec)
                print(f"{or_minutes:>6} {tp:>5} {direction:>5} | {e['n']:>5} "
                      f"{e['win_rate']*100:>5.1f} {e['mean_r']:>7.3f} {e['profit_factor']:>6.2f} "
                      f"{e['total_r']:>8.1f} {str(e['boot_p_value']):>6} "
                      f"{w['frac_folds_positive']*100:>6.0f}% {'PASS' if w['gate_pass'] else 'fail'}")


if __name__ == "__main__":
    main()
