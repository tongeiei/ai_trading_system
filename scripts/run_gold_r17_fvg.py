"""R17 — FVG (Fair Value Gap) — DEV grid + sacred DEV/HOLDOUT + cost stress.

docs/research/R15_R17_SMC_PLAN.md, R17.

Mandatory baselines per plan §7: R11 (wick-fill, already falsified — same
"fade an imbalance after a fast move" family) and plain mean-reversion. If
FVG does not clear both by a meaningful margin, "filling the gap" adds
nothing over ordinary mean-reversion.

  PYTHONPATH=. .venv/bin/python -u scripts/run_gold_r17_fvg.py           # 3y smoke
  PYTHONPATH=. .venv/bin/python -u scripts/run_gold_r17_fvg.py --full    # 2006-2018 DEV grid
  PYTHONPATH=. .venv/bin/python -u scripts/run_gold_r17_fvg.py --holdout # sacred DEV/HOLDOUT (single run)
"""
from __future__ import annotations

import copy
import sys

from src.backtest.gold_harness import (
    load_spec, load_gold_data, build_features,
    label_all_signals, apply_gold_costs, evaluate, walk_forward,
)
from src.strategy.gold_r17_fvg import generate_r17_signals

DEV_START, DEV_END = "2006-01-01", "2018-12-31"
HOLD_START, HOLD_END = "2019-01-01", None

# Placeholder until filled in by hand from the DEV grid gradient (§2 plateau
# check) -- see docs/research/artifacts/xau_r17_fvg.txt once it exists.
FROZEN_CFG: dict = dict(k_gap=0.5, N=10, tp_r_mult=1.5, direction="both")


def cost_scaled_spec(spec: dict, mult: float) -> dict:
    s = copy.deepcopy(spec)
    c = s["costs"]
    c["spread_bps_per_side"] = c["spread_bps_per_side"] * mult
    c["slippage_bps_per_side"] = c["slippage_bps_per_side"] * mult
    return s


def row(label, e, w):
    if e.get("n", 0) == 0:
        print(f"{label:>50} | n=0 (no trades)")
        return
    print(f"{label:>50} | n={e['n']:>5} win%={e['win_rate']*100:>5.1f} "
          f"meanR={e['mean_r']:>7.4f} PF={e['profit_factor']:>6.2f} "
          f"totR={e['total_r']:>8.1f} folds+={w.get('frac_folds_positive', 0)*100:>5.1f}% "
          f"folds_counted={w.get('n_folds_counted', 0):>3} "
          f"GATE={'PASS' if w.get('gate_pass') else 'fail'}")


def eval_at_costs(labeled, spec):
    out = {}
    for tag, mult in (("base", 1.0), ("2x", 2.0), ("3x", 3.0)):
        s = cost_scaled_spec(spec, mult) if mult != 1.0 else spec
        costed = apply_gold_costs(labeled, s)
        e, w = evaluate(costed), walk_forward(costed, s)
        out[tag] = (e, w)
    return out


def run_signals(m15, m1, spec, **cfg):
    sig = generate_r17_signals(m15, **cfg)
    live = sig[sig["action"] != "NO_TRADE"].copy() if not sig.empty else sig
    if live.empty:
        return live
    labeled = label_all_signals(live, m1)
    return labeled


def smoke(spec):
    print("########## SMOKE (2022-08-01 .. end) ##########")
    m15, h1, m1 = load_gold_data(spec, "2022-08-01", None)
    print(f"[smoke] m15={len(m15):,} m1={len(m1):,}")
    labeled = run_signals(m15, m1, spec, atr_len=14, buf=0.1, session_filter=True, **FROZEN_CFG)
    if labeled.empty:
        print("SMOKE: no trades")
        return
    costed = apply_gold_costs(labeled, spec)
    e, w = evaluate(costed), walk_forward(costed, spec)
    row(f"SMOKE {FROZEN_CFG}", e, w)


def full_grid(spec):
    print("########## FULL DEV-window GRID (2006-01-01 .. 2018-12-31) ##########")
    m15, h1, m1 = load_gold_data(spec, DEV_START, DEV_END)
    print(f"[dev] m15={len(m15):,} h1={len(h1):,} m1={len(m1):,}")
    _ = build_features(m15, h1)

    print(f"\n{'kgap':>5} {'N':>3} {'tp':>5} {'dir':>5} | {'n':>5} {'win%':>6} "
          f"{'meanR':>8} {'PF':>6} {'totR':>8} {'folds+':>7} {'foldsN':>7} GATE")
    grid_rows = []
    for k_gap in (0.3, 0.5, 0.8):
        for N in (5, 10, 20):
            for tp_r_mult in (1.0, 1.5, 2.0):
                for direction in ("both", "long"):
                    cfg = dict(atr_len=14, buf=0.1, k_gap=k_gap, N=N,
                               tp_r_mult=tp_r_mult, direction=direction, session_filter=True)
                    labeled = run_signals(m15, m1, spec, **cfg)
                    if labeled.empty:
                        print(f"{k_gap:>5} {N:>3} {tp_r_mult:>5} {direction:>5} | (no trades)")
                        continue
                    costed = apply_gold_costs(labeled, spec)
                    e, wfo = evaluate(costed), walk_forward(costed, spec)
                    grid_rows.append((cfg, e, wfo))
                    print(f"{k_gap:>5} {N:>3} {tp_r_mult:>5} {direction:>5} | {e['n']:>5} "
                          f"{e['win_rate']*100:>5.1f} {e['mean_r']:>8.4f} {e['profit_factor']:>6.2f} "
                          f"{e['total_r']:>8.1f} {wfo['frac_folds_positive']*100:>6.0f}% "
                          f"{wfo.get('n_folds_counted', 0):>7} "
                          f"{'PASS' if wfo['gate_pass'] else 'fail'}")
    return grid_rows


def sacred_holdout(spec):
    print(f"[R17 HOLDOUT] frozen config: {FROZEN_CFG}")

    print("\n########## DEV (2006-01-01 .. 2018-12-31) ##########")
    m15_dev, h1_dev, m1_dev = load_gold_data(spec, DEV_START, DEV_END)
    print(f"[dev] m15={len(m15_dev):,} m1={len(m1_dev):,}")
    labeled_dev = run_signals(m15_dev, m1_dev, spec, atr_len=14, buf=0.1, session_filter=True, **FROZEN_CFG)
    print(f"[dev] tradeable/labeled: {len(labeled_dev):,}")

    print("\n-- DEV cost stress (frozen config) --")
    dev_costs = eval_at_costs(labeled_dev, spec)
    for tag in ("base", "2x", "3x"):
        e, w = dev_costs[tag]
        row(f"DEV [{tag}]", e, w)
    dev_base_e, dev_base_w = dev_costs["base"]

    del m15_dev, h1_dev, m1_dev, labeled_dev

    print("\n########## HOLDOUT (2019-01-01 .. end of data) — SINGLE RUN, frozen config ONLY ##########")
    m15_h, h1_h, m1_h = load_gold_data(spec, HOLD_START, HOLD_END)
    print(f"[holdout] m15={len(m15_h):,} m1={len(m1_h):,}")
    labeled_h = run_signals(m15_h, m1_h, spec, atr_len=14, buf=0.1, session_filter=True, **FROZEN_CFG)
    print(f"[holdout] tradeable/labeled: {len(labeled_h):,}")

    print("\n-- HOLDOUT cost stress (frozen config) --")
    hold_costs = eval_at_costs(labeled_h, spec)
    for tag in ("base", "2x", "3x"):
        e, w = hold_costs[tag]
        row(f"HOLDOUT [{tag}]", e, w)
    hold_base_e, hold_base_w = hold_costs["base"]

    print("\n########## GATE CHECK (pre-committed, same discipline as R2/R8/R11/R14/R15) ##########")
    g1 = dev_base_w.get("gate_pass", False)
    print(f"1. DEV harness gate (PF>=1.10 & folds+>=60%): {'PASS' if g1 else 'FAIL'} "
          f"(PF={dev_base_e.get('profit_factor', float('nan')):.3f} "
          f"folds+={dev_base_w.get('frac_folds_positive', 0)*100:.1f}%)")

    print("2. Sensitivity plateau vs spike: judged from the DEV grid (see --full output) — "
          "manual/verdict call in report text.")

    hg_pf = hold_base_e.get("profit_factor", float("nan")) if hold_base_e.get("n", 0) else float("nan")
    hg_fp = hold_base_w.get("frac_folds_positive", 0.0)
    g3 = hold_base_e.get("n", 0) > 0 and hg_pf >= 1.10 and hg_fp >= 0.55
    print(f"3. HOLDOUT gate (PF>=1.10 & folds+>=55%, base cost): {'PASS' if g3 else 'FAIL'} "
          f"(PF={hg_pf} folds+={hg_fp*100:.1f}%)")

    dev_mean_r = dev_base_e.get("mean_r", float("nan"))
    hold_mean_r = hold_base_e.get("mean_r", float("nan")) if hold_base_e.get("n", 0) else float("nan")
    g4 = (hold_base_e.get("n", 0) > 0 and hold_mean_r >= 0
          and (dev_mean_r <= 0 or hold_mean_r >= 0.60 * dev_mean_r))
    print(f"4. HOLDOUT degradation (hold mean_r>=0 and >=60% of DEV mean_r): "
          f"{'PASS' if g4 else 'FAIL'} (dev_mean_r={dev_mean_r:.4f} hold_mean_r={hold_mean_r})")

    dev_2x_e, dev_2x_w = dev_costs["2x"]
    hold_2x_e, hold_2x_w = hold_costs["2x"]
    dev_2x_pf = dev_2x_e.get("profit_factor", float("nan")) if dev_2x_e.get("n", 0) else float("nan")
    hold_2x_pf = hold_2x_e.get("profit_factor", float("nan")) if hold_2x_e.get("n", 0) else float("nan")
    g5 = (dev_2x_e.get("n", 0) > 0 and dev_2x_pf >= 1.10
          and hold_2x_e.get("n", 0) > 0 and hold_2x_pf >= 1.10)
    print(f"5. Cost stress survival at 2x (DEV & HOLDOUT PF>=1.10): {'PASS' if g5 else 'FAIL'} "
          f"(dev_2x_PF={dev_2x_pf} hold_2x_PF={hold_2x_pf})")

    n_hold = hold_base_e.get("n", 0)
    nf_hold = hold_base_w.get("n_folds_counted", 0)
    g6 = n_hold >= 200 and nf_hold >= 8
    print(f"6. Sample size (holdout n>=200 & folds_counted>=8): {'PASS' if g6 else 'FAIL/NEEDS_MORE'} "
          f"(n={n_hold} folds_counted={nf_hold})")

    core_pass = g1 and g3 and g4 and g5
    if not core_pass:
        verdict = "FAIL"
    elif not g6:
        verdict = "NEEDS_MORE_TESTING"
    else:
        verdict = "PASS (pending manual §2 plateau check from the --full grid)"
    print(f"\n=== VERDICT (mechanical gate items 1,3,4,5,6): {verdict} ===")


def main() -> None:
    spec = load_spec()
    print(f"cost (bps/side, base): spread={spec['costs']['spread_bps_per_side']} "
          f"slip={spec['costs']['slippage_bps_per_side']} "
          f"comm={spec['costs']['commission_bps_per_side']} (no funding, spot)")

    if "--full" in sys.argv:
        full_grid(spec)
    elif "--holdout" in sys.argv:
        sacred_holdout(spec)
    else:
        smoke(spec)


if __name__ == "__main__":
    main()
