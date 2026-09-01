"""R2 sacred DEV/HOLDOUT evaluation — docs/research/R2_HOLDOUT_PLAN.md.

Frozen config (plan §1): or_start_hour=7, or_minutes=60, fib_ratio=0.618,
tp_r_mult=1.5, direction=long, cutoff_hour=16.

DEV   = 2006-01-01 .. 2018-12-31 (unlimited touches, sensitivity grid here)
HOLDOUT = 2019-01-01 .. 2026-08-27 (run EXACTLY ONCE, no re-runs)

  PYTHONPATH=. .venv/bin/python -u scripts/run_gold_r2_holdout.py

Writes nothing itself besides stdout; caller redirects to the artifact file.
"""
from __future__ import annotations

import copy

from src.backtest.gold_harness import (
    load_spec, load_gold_data, build_features,
    label_all_signals, apply_gold_costs, evaluate, walk_forward,
)
from src.strategy.gold_orb_pullback import generate_orb_pullback_signals

CFG1 = dict(or_start_hour=7, or_minutes=60, fib_ratio=0.618, tp_r_mult=1.5,
            direction="long", cutoff_hour=16)

DEV_START, DEV_END = "2006-01-01", "2018-12-31"
HOLD_START, HOLD_END = "2019-01-01", None  # None -> end of available data (2026-08-27)


def cost_scaled_spec(spec: dict, mult: float) -> dict:
    s = copy.deepcopy(spec)
    c = s["costs"]
    c["spread_bps_per_side"] = c["spread_bps_per_side"] * mult
    c["slippage_bps_per_side"] = c["slippage_bps_per_side"] * mult
    return s


def row(label, e, w):
    if e.get("n", 0) == 0:
        print(f"{label:>28} | n=0 (no trades)")
        return
    print(f"{label:>28} | n={e['n']:>5} win%={e['win_rate']*100:>5.1f} "
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


def main() -> None:
    spec = load_spec()
    print(f"cost (bps/side, base): spread={spec['costs']['spread_bps_per_side']} "
          f"slip={spec['costs']['slippage_bps_per_side']} "
          f"comm={spec['costs']['commission_bps_per_side']} (no funding, spot)")
    print(f"[R2 HOLDOUT PLAN] frozen config §1: {CFG1}")

    # ------------------------------------------------------------------ DEV
    print("\n########## DEV (2006-01-01 .. 2018-12-31) ##########")
    m15_dev, h1_dev, m1_dev = load_gold_data(spec, DEV_START, DEV_END)
    print(f"[dev] m15={len(m15_dev):,} h1={len(h1_dev):,} m1={len(m1_dev):,}")
    _ = build_features(m15_dev, h1_dev)  # parity w/ contract, unused by ORB rule

    sig_dev = generate_orb_pullback_signals(m15_dev, **CFG1)
    live_dev = sig_dev[sig_dev["action"] != "NO_TRADE"].copy() if not sig_dev.empty else sig_dev
    print(f"[dev] tradeable signals: {len(live_dev):,}")
    labeled_dev = label_all_signals(live_dev, m1_dev)

    print("\n-- DEV cost stress (config §1) --")
    dev_costs = eval_at_costs(labeled_dev, spec)
    for tag in ("base", "2x", "3x"):
        e, w = dev_costs[tag]
        row(f"DEV cfg1 [{tag}]", e, w)

    dev_base_e, dev_base_w = dev_costs["base"]

    # ------------------------------------------------------- DEV sensitivity
    print("\n########## DEV sensitivity grid (§4, base cost) ##########")
    print(f"{'or':>3} {'fib':>5} {'tp':>4} {'dir':>5} | {'n':>5} {'win%':>6} {'meanR':>8} "
          f"{'PF':>6} {'totR':>8} {'folds+':>7} {'foldsN':>7} GATE")
    grid_rows = []
    for or_minutes in (30, 60):
        for fib in (0.5, 0.618, 0.75):
            for tp in (1.0, 1.5, 2.0):
                for direction in ("long", "both"):
                    sig = generate_orb_pullback_signals(
                        m15_dev, or_start_hour=CFG1["or_start_hour"], or_minutes=or_minutes,
                        cutoff_hour=CFG1["cutoff_hour"], fib_ratio=fib, tp_r_mult=tp,
                        direction=direction)
                    live = sig[sig["action"] != "NO_TRADE"].copy() if not sig.empty else sig
                    if live.empty:
                        print(f"{or_minutes:>3} {fib:>5} {tp:>4} {direction:>5} | (no trades)")
                        continue
                    labeled = label_all_signals(live, m1_dev)
                    costed = apply_gold_costs(labeled, spec)
                    e, w = evaluate(costed), walk_forward(costed, spec)
                    grid_rows.append((or_minutes, fib, tp, direction, e, w))
                    print(f"{or_minutes:>3} {fib:>5} {tp:>4} {direction:>5} | {e['n']:>5} "
                          f"{e['win_rate']*100:>5.1f} {e['mean_r']:>8.4f} {e['profit_factor']:>6.2f} "
                          f"{e['total_r']:>8.1f} {w['frac_folds_positive']*100:>6.0f}% "
                          f"{w.get('n_folds_counted', 0):>7} "
                          f"{'PASS' if w['gate_pass'] else 'fail'}")

    del m15_dev, h1_dev, m1_dev, labeled_dev, live_dev, sig_dev

    # -------------------------------------------------------------- HOLDOUT
    print("\n########## HOLDOUT (2019-01-01 .. end of data) — SINGLE RUN, config §1 ONLY ##########")
    m15_h, h1_h, m1_h = load_gold_data(spec, HOLD_START, HOLD_END)
    print(f"[holdout] m15={len(m15_h):,} h1={len(h1_h):,} m1={len(m1_h):,}")
    _ = build_features(m15_h, h1_h)

    sig_h = generate_orb_pullback_signals(m15_h, **CFG1)
    live_h = sig_h[sig_h["action"] != "NO_TRADE"].copy() if not sig_h.empty else sig_h
    print(f"[holdout] tradeable signals: {len(live_h):,}")
    labeled_h = label_all_signals(live_h, m1_h)

    print("\n-- HOLDOUT cost stress (config §1) --")
    hold_costs = eval_at_costs(labeled_h, spec)
    for tag in ("base", "2x", "3x"):
        e, w = hold_costs[tag]
        row(f"HOLDOUT cfg1 [{tag}]", e, w)

    hold_base_e, hold_base_w = hold_costs["base"]

    # --------------------------------------------------------------- gate
    print("\n########## GATE CHECK (§6, pre-committed) ##########")
    g1 = dev_base_w.get("gate_pass", False)
    print(f"1. DEV harness gate (PF>=1.10 & folds+>=60%): {'PASS' if g1 else 'FAIL'} "
          f"(PF={dev_base_e.get('profit_factor'):.3f} folds+={dev_base_w.get('frac_folds_positive', 0)*100:.1f}%)")

    print("2. Sensitivity plateau vs spike: see grid above — manual/verdict call in report text "
          "(neighbours of fib=0.618,tp=1.5,or=60,dir=long must not be all-negative; "
          "fib=0.75 must not keep improving without bound).")

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

    core_pass = g1 and g3 and g4 and g5  # gate item 2 is judged qualitatively in the text report
    if not core_pass:
        verdict = "FAIL"
    elif not g6:
        verdict = "NEEDS_MORE_TESTING"
    else:
        verdict = "PASS (pending manual §2 plateau check above)"
    print(f"\n=== VERDICT (mechanical gate items 1,3,4,5,6): {verdict} ===")
    print("NOTE: item 2 (plateau vs spike) requires reading the DEV sensitivity table above; "
          "not auto-scored here.")


if __name__ == "__main__":
    main()
