"""Phase 7 — max-hold barrier extension, pre-registered plan:
docs/research/ETH_PHASE7_HOLD_PLAN.md

Tests whether the live 12h timeout is a binding constraint on V0 (locked
ADX35/SL2.5/TP2R) by re-labeling the SAME signal set at longer barriers
{12h(control), 18h, 24h, 36h, 48h} and checking whether net expectancy
improves without the red flags the plan pre-registers as reject criteria.

Runs on ETH (primary) and XRP (replication — mechanism ties to the exit
rule itself, not one symbol's history, so both must show the same shape).

Does not touch any live constant. Output only.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs, commission_cost_r, slippage_cost_r, SLIPPAGE_BPS, TAKER_FEE
from src.backtest.significance import bootstrap_mean_test

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

LOCKED_CONFIG = {"adx": 35, "sl": 2.5}
HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")  # matches research_xrp_vetting.py
CAL_FOLD_START = pd.Timestamp("2025-01-01", tz="UTC")  # matches live SYMBOL_STATS derivation window
CAL_FOLD_END = pd.Timestamp("2025-07-01", tz="UTC")
EV_THRESHOLD_R = 0.15  # src/live/ev_estimate.py EV_THRESHOLD_R — do not diverge without updating both

HOLD_GRID_HOURS = [12, 18, 24, 36, 48]  # 12h is the control (= current live value)
DEV_GATE_PF = 1.10
DEV_GATE_FOLD_PCT = 0.60
COST_STRESS_MULT = 2.0


def load_symbol_data(symbol_prefix: str):
    m15 = pd.read_parquet(f"data/raw/{symbol_prefix}_15m.parquet")
    h1 = pd.read_parquet(f"data/raw/{symbol_prefix}_1h.parquet")
    m1 = pd.read_parquet(f"data/raw/{symbol_prefix}_1m.parquet")
    funding = pd.read_parquet(f"data/raw/{symbol_prefix}_USDT_funding.parquet")
    return m15, h1, m1, funding


def build_trade_universe(m15, h1):
    """Same signal set is reused across every max_hold — only the labeling
    barrier changes, so grid cells are directly comparable (no confound from
    a different trigger firing on different bars)."""
    features = build_features(m15, h1)
    regime = classify_regime(features, adx_threshold=LOCKED_CONFIG["adx"])
    signals = generate_v0_signals(m15, features, regime, sl_atr_mult=LOCKED_CONFIG["sl"])
    return signals[signals["action"] != "NO_TRADE"].copy()


def net_pf(df: pd.DataFrame) -> float:
    gross_win = df.loc[df["net_r_multiple"] > 0, "net_r_multiple"].sum()
    gross_loss = -df.loc[df["net_r_multiple"] < 0, "net_r_multiple"].sum()
    return gross_win / gross_loss if gross_loss > 0 else float("inf")


def quarterly_wfo(costed: pd.DataFrame, embargo: pd.Timedelta) -> dict:
    """Anchored quarterly folds over the full history, embargoed by the
    max_hold under test (a longer hold needs a wider embargo — a trade
    entered near a fold boundary can now resolve well past it)."""
    start = costed["time_utc"].min().to_period("Q").start_time.tz_localize("UTC")
    end = costed["time_utc"].max()
    bounds = pd.date_range(start, end + pd.Timedelta(days=1), freq="QS", tz="UTC")

    fold_means = []
    for i in range(len(bounds) - 1):
        fold_start, fold_end = bounds[i], bounds[i + 1]
        in_fold = (costed["time_utc"] >= fold_start + embargo) & (costed["time_utc"] < fold_end - embargo)
        fold_trades = costed[in_fold]
        if len(fold_trades) == 0:
            continue
        fold_means.append(fold_trades["net_r_multiple"].mean())

    n_folds = len(fold_means)
    n_positive = sum(1 for m in fold_means if m > 0)
    return {"n_folds": n_folds, "n_positive": n_positive, "pct_positive": n_positive / n_folds if n_folds else 0.0}


def cost_stress(labeled: pd.DataFrame, funding: pd.DataFrame, dev_mask: pd.Series, mult: float) -> float:
    """Recompute net PF on DEV at `mult`x the base commission+slippage — same
    approach as eth_walkforward_and_slippage.py's slippage-sensitivity check."""
    stressed = labeled.copy()
    stressed["commission_r"] = stressed.apply(
        lambda r: commission_cost_r(r["sl_distance"], r["close"], TAKER_FEE * mult), axis=1)
    stressed["slippage_r"] = stressed.apply(
        lambda r: slippage_cost_r(r["sl_distance"], r["close"], SLIPPAGE_BPS * mult), axis=1)
    from src.backtest.costs import funding_cost_r
    stressed["funding_r"] = stressed.apply(
        lambda r: funding_cost_r(r["time_utc"], r["exit_time"], r["close"], r["action"], r["sl_distance"], funding),
        axis=1)
    stressed["net_r_multiple"] = stressed["r_multiple"] - stressed["commission_r"] - stressed["slippage_r"] - stressed["funding_r"]
    return net_pf(stressed[dev_mask])


def ev_gate_relevance(labeled_gross: pd.DataFrame) -> dict:
    """Recompute win_rate/avg_win_r/avg_loss_r on the SAME CAL fold window
    (2025-01..2025-06) the live SYMBOL_STATS were derived from, then compute
    ev_r the same way src/live/ev_estimate.py does: gross stats minus mean
    commission+slippage cost (funding excluded from the live gate — matching
    that behavior here, not adding a stricter check under a different name).
    """
    cal = labeled_gross[(labeled_gross["time_utc"] >= CAL_FOLD_START) & (labeled_gross["time_utc"] < CAL_FOLD_END)]
    if cal.empty:
        return {"n": 0, "ev_r": float("nan"), "passes_gate": False}

    wins = cal[cal["label"] == 1]
    losses = cal[cal["label"] == 0]
    win_rate = len(wins) / len(cal)
    avg_win_r = wins["r_multiple"].mean() if len(wins) else 0.0
    avg_loss_r = -losses["r_multiple"].mean() if len(losses) else 0.0

    mean_cost_r = cal.apply(
        lambda r: commission_cost_r(r["sl_distance"], r["close"], TAKER_FEE) + slippage_cost_r(r["sl_distance"], r["close"]),
        axis=1
    ).mean()
    ev_r = win_rate * avg_win_r - (1 - win_rate) * avg_loss_r - mean_cost_r
    return {"n": len(cal), "win_rate": win_rate, "avg_win_r": avg_win_r, "avg_loss_r": avg_loss_r,
            "cost_r": mean_cost_r, "ev_r": ev_r, "passes_gate": ev_r >= EV_THRESHOLD_R}


def resolution_rate(labeled: pd.DataFrame) -> float:
    return (labeled["exit_reason"] != "TIMEOUT").mean()


def run_symbol(symbol_name: str, symbol_prefix: str) -> pd.DataFrame:
    print(f"\n{'='*20} {symbol_name} {'='*20}")
    m15, h1, m1, funding = load_symbol_data(symbol_prefix)
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=max(HOLD_GRID_HOURS))
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)

    trades = build_trade_universe(m15, h1)
    print(f"trade universe: {len(trades)} candidates (same signals reused for every hold)")

    rows = []
    for hold_h in HOLD_GRID_HOURS:
        max_hold_bars = hold_h * 60
        labeled = label_all_signals(trades, m1, max_hold_bars=max_hold_bars).dropna(subset=["label"])
        labeled["time_utc"] = pd.to_datetime(labeled["time_utc"])
        costed = apply_costs(labeled, funding)

        dev_mask = costed["time_utc"] < HOLDOUT_START
        dev = costed[dev_mask]
        holdout = costed[~dev_mask]

        dev_pf = net_pf(dev)
        wfo = quarterly_wfo(dev, embargo=pd.Timedelta(hours=hold_h))
        stress_pf = cost_stress(labeled, funding, dev_mask, COST_STRESS_MULT)
        dev_gate_pass = dev_pf >= DEV_GATE_PF and wfo["pct_positive"] >= DEV_GATE_FOLD_PCT
        stress_pass = stress_pf >= DEV_GATE_PF

        holdout_pf = net_pf(holdout) if len(holdout) else float("nan")
        boot = bootstrap_mean_test(holdout["net_r_multiple"].to_numpy()) if len(holdout) else None

        resolved_dev = resolution_rate(labeled[dev_mask])
        ev_check = ev_gate_relevance(labeled)

        rows.append({
            "hold_h": hold_h,
            "n_dev": len(dev), "n_holdout": len(holdout),
            "dev_pf": dev_pf, "dev_fold_pct_pos": wfo["pct_positive"], "dev_n_folds": wfo["n_folds"],
            "cost_stress_2x_pf": stress_pf,
            "dev_gate_pass": dev_gate_pass, "cost_stress_pass": stress_pass,
            "holdout_pf": holdout_pf,
            "holdout_mean_r": boot["observed_mean"] if boot else float("nan"),
            "holdout_ci_lo": boot["ci_95_lo"] if boot else float("nan"),
            "holdout_ci_hi": boot["ci_95_hi"] if boot else float("nan"),
            "holdout_p": boot["p_value"] if boot else float("nan"),
            "holdout_significant": boot["significant_at_5pct"] if boot else False,
            "resolution_rate_dev": resolved_dev,
            "ev_r_cal_fold": ev_check["ev_r"], "ev_gate_pass": ev_check["passes_gate"],
        })

        print(f"\n--- hold={hold_h}h (max_hold_bars={max_hold_bars}) ---")
        print(f"DEV:      n={len(dev):5d}  PF={dev_pf:.3f}  folds+={wfo['n_positive']}/{wfo['n_folds']} "
              f"({wfo['pct_positive']:.0%})  resolution_rate={resolved_dev:.1%}  gate={'PASS' if dev_gate_pass else 'fail'}")
        print(f"COST 2x:  PF={stress_pf:.3f}  {'PASS' if stress_pass else 'fail'}")
        if boot:
            sig = "PASS" if boot["significant_at_5pct"] else "fail"
            print(f"HOLDOUT:  n={len(holdout):5d}  PF={holdout_pf:.3f}  mean_r={boot['observed_mean']:+.4f} "
                  f"CI=[{boot['ci_95_lo']:+.4f},{boot['ci_95_hi']:+.4f}]  p={boot['p_value']:.4f}  {sig}")
        print(f"EV-GATE:  CAL-fold(2025H1) n={ev_check['n']}  ev_r={ev_check['ev_r']:+.4f}R vs {EV_THRESHOLD_R}R  "
              f"{'PASS' if ev_check['passes_gate'] else 'fail'}")

    result = pd.DataFrame(rows)

    print(f"\n--- {symbol_name}: gradient across grid (kill-criteria check) ---")
    print(result[["hold_h", "dev_pf", "cost_stress_2x_pf", "holdout_mean_r", "resolution_rate_dev", "ev_r_cal_fold"]]
          .to_string(index=False))

    pf_series = result["dev_pf"].to_numpy()
    monotonic_increasing = np.all(np.diff(pf_series) >= -1e-9)
    still_climbing_at_max = pf_series[-1] > pf_series[-2]
    if monotonic_increasing and still_climbing_at_max:
        print("\n*** WARNING: runaway optimum — PF still climbing at the longest hold tested, "
              "no plateau. Per plan §5, this REJECTS the whole grid (looks like unbounded "
              "trend-following, not a fix to the barrier). ***")

    resolution_series = result["resolution_rate_dev"].to_numpy()
    if resolution_series[-1] < 0.95:
        print(f"\n*** WARNING: resolution rate at {HOLD_GRID_HOURS[-1]}h is only "
              f"{resolution_series[-1]:.1%} (<95%) — barrier may not have been binding as "
              f"hypothesized. Per plan §5, weakens confidence in mechanism. ***")

    return result


if __name__ == "__main__":
    eth_result = run_symbol("ETH", "ETHUSDT")
    xrp_result = run_symbol("XRP", "XRPUSDT")

    out_path = Path("docs/research/artifacts/eth_phase7_hold_extension.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined = pd.concat(
        [eth_result.assign(symbol="ETH"), xrp_result.assign(symbol="XRP")],
        ignore_index=True,
    )
    combined.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path}")
