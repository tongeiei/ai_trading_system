"""Phase 3 of docs/PLAN_CUSTOM.md — independent validation of a second
TREND strategy candidate, per research question 4.

PLAN_CUSTOM: "The existing breakout strategy may be used as a starting
point, but independently validate it. V0 remains unchanged. A new strategy
should only become eligible for live consideration if it demonstrates
independent positive expectancy and robust WFO performance."

This tests ONE hypothesis — src/strategy/breakout.py's existing Donchian(20)
breakout, UNCHANGED (Donchian period 20, ADX_MIN=20 on H1, SL=2.0x ATR,
TP=2R) — as-is, no parameter sweep, to avoid inflating the multiple-testing
count with a tuned variant. It was previously tested only on BTC
(single-split, PF~0.52, rejected — see docs/FINDINGS.md) and never
independently validated on ETH, which is what this phase does.

Same rigor as V0: research pool only (< SACRED_HOLDOUT_START), full cost
model, quarterly anchored WFO with 12h embargo, bootstrap significance.
Also reports overlap with V0 baseline trade timing, since a genuinely
"independent" second strategy should mostly fire in different moments than
V0, not duplicate/correlate with it (relevant to the portfolio-risk
question if this or another candidate is ever promoted).

Does not modify src/strategy/breakout.py or src/strategy/v0_rules.py.
"""
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.breakout import generate_breakout_signals
from src.strategy.v0_rules import generate_v0_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs
from src.backtest.significance import bootstrap_mean_test

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

LOCKED_V0_CONFIG = {"adx": 35, "sl": 2.5}  # for regime labeling + the V0 overlap comparison only
SACRED_HOLDOUT_START = pd.Timestamp("2026-07-01", tz="UTC")
EMBARGO = pd.Timedelta(hours=12)


def load_data():
    m15 = pd.read_parquet("data/raw/ETHUSDT_15m.parquet")
    h1 = pd.read_parquet("data/raw/ETHUSDT_1h.parquet")
    m1 = pd.read_parquet("data/raw/ETHUSDT_1m.parquet")
    funding = pd.read_parquet("data/raw/ETHUSDT_USDT_funding.parquet")
    return m15, h1, m1, funding


def max_drawdown_r(net_r_sorted_by_time: pd.Series) -> float:
    equity = net_r_sorted_by_time.cumsum()
    return (equity - equity.cummax()).min()


def summarize(name, costed):
    n = len(costed)
    if n == 0:
        print(f"\n=== {name}: NO TRADES ===")
        return None
    costed = costed.sort_values("exit_time")
    win_rate = (costed["net_r_multiple"] > 0).mean()
    avg_win = costed.loc[costed["net_r_multiple"] > 0, "net_r_multiple"].mean()
    avg_loss = costed.loc[costed["net_r_multiple"] < 0, "net_r_multiple"].mean()
    expectancy = costed["net_r_multiple"].mean()
    gross_win = costed.loc[costed["net_r_multiple"] > 0, "net_r_multiple"].sum()
    gross_loss = -costed.loc[costed["net_r_multiple"] < 0, "net_r_multiple"].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    max_dd = max_drawdown_r(costed["net_r_multiple"])
    n_years = (costed["time_utc"].max() - costed["time_utc"].min()).days / 365.25
    long_r = costed.loc[costed["action"] == "LONG", "net_r_multiple"]
    short_r = costed.loc[costed["action"] == "SHORT", "net_r_multiple"]
    bs = bootstrap_mean_test(costed["net_r_multiple"].to_numpy(), n_resamples=5000, seed=1)

    print(f"\n=== {name} ===")
    print(f"n={n}  trades/year={n/n_years:.1f}  win_rate={win_rate:.1%}  "
          f"avg_win={avg_win:.3f}R  avg_loss={avg_loss:.3f}R  expectancy={expectancy:.4f}R  PF={pf:.3f}")
    print(f"MaxDD={max_dd:.2f}R  LONG: n={len(long_r)} avg={long_r.mean():.4f}R  "
          f"SHORT: n={len(short_r)} avg={short_r.mean():.4f}R")
    print(f"Bootstrap: mean={bs['observed_mean']:.4f}, 95% CI=[{bs['ci_95_lo']:.4f}, {bs['ci_95_hi']:.4f}], "
          f"p={bs['p_value']:.4f} ({'significant' if bs['significant_at_5pct'] else 'not significant'})")

    return {
        "variant": name, "n": n, "trades_per_year": n / n_years, "win_rate": win_rate,
        "avg_win_r": avg_win, "avg_loss_r": avg_loss, "expectancy_r": expectancy, "pf": pf,
        "max_dd_r": max_dd, "bootstrap_p": bs["p_value"], "significant": bs["significant_at_5pct"],
        "ci_lo": bs["ci_95_lo"], "ci_hi": bs["ci_95_hi"],
    }


def wfo_folds(name, costed):
    if len(costed) == 0:
        return pd.DataFrame()
    costed = costed.copy()
    costed["time_utc"] = pd.to_datetime(costed["time_utc"])
    start = costed["time_utc"].min().tz_convert("UTC").to_period("Q").start_time.tz_localize("UTC")
    end = costed["time_utc"].max()
    fold_bounds = pd.date_range(start, end + pd.Timedelta(days=1), freq="QS", tz="UTC")

    rows = []
    for i in range(len(fold_bounds) - 1):
        fold_start, fold_end = fold_bounds[i], fold_bounds[i + 1]
        in_fold = (costed["time_utc"] >= fold_start + EMBARGO) & (costed["time_utc"] < fold_end - EMBARGO)
        ft = costed[in_fold]
        if len(ft) == 0:
            continue
        win_rate = (ft["net_r_multiple"] > 0).mean()
        net_avg = ft["net_r_multiple"].mean()
        gw = ft.loc[ft["net_r_multiple"] > 0, "net_r_multiple"].sum()
        gl = -ft.loc[ft["net_r_multiple"] < 0, "net_r_multiple"].sum()
        pf = gw / gl if gl > 0 else float("inf")
        rows.append({"fold": f"{fold_start.date()}", "n": len(ft), "win_rate": win_rate, "net_avg_r": net_avg, "pf": pf})

    fold_df = pd.DataFrame(rows)
    valid = fold_df[fold_df["n"] >= 20]
    if len(valid) == 0:
        print(f"{name}: no folds with n>=20 trades")
        return fold_df
    n_pos = (valid["net_avg_r"] > 0).sum()
    print(f"{name}: WFO folds n>=20: {len(valid)}, positive: {n_pos} ({n_pos/len(valid):.0%}), "
          f"worst={valid['net_avg_r'].min():.4f}, best={valid['net_avg_r'].max():.4f}, "
          f"std={valid['net_avg_r'].std():.4f}")
    return fold_df


def overlap_stats(v0_costed, breakout_costed):
    """How much do the two strategies' trades share the same time window?
    A truly 'independent situation' should mostly NOT overlap."""
    v0_windows = list(zip(v0_costed["time_utc"], v0_costed["exit_time"]))
    bo_windows = list(zip(breakout_costed["time_utc"], breakout_costed["exit_time"]))

    def overlaps(a, b):
        return a[0] < b[1] and b[0] < a[1]

    v0_sorted = sorted(v0_windows, key=lambda w: w[0])
    bo_sorted = sorted(bo_windows, key=lambda w: w[0])
    overlap_count = 0
    j = 0
    for bo in bo_sorted:
        while j < len(v0_sorted) and v0_sorted[j][1] <= bo[0]:
            j += 1
        k = j
        while k < len(v0_sorted) and v0_sorted[k][0] < bo[1]:
            if overlaps(v0_sorted[k], bo):
                overlap_count += 1
                break
            k += 1
    pct = 100 * overlap_count / len(bo_sorted) if bo_sorted else 0.0
    print(f"\nBreakout trades whose holding window overlaps a concurrent V0 trade: "
          f"{overlap_count}/{len(bo_sorted)} ({pct:.1f}%)")


def main():
    m15, h1, m1, funding = load_data()
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)
    pool_mask = m15["time_utc"] < SACRED_HOLDOUT_START
    m15_pool = m15[pool_mask].reset_index(drop=True)
    h1_pool = h1[h1["time_utc"] < SACRED_HOLDOUT_START].reset_index(drop=True)

    features = build_features(m15_pool, h1_pool)
    regime = classify_regime(features, adx_threshold=LOCKED_V0_CONFIG["adx"])

    # --- V0 baseline, for overlap comparison only (same as Phase 1/2 control) ---
    v0_signals = generate_v0_signals(m15_pool, features, regime, sl_atr_mult=LOCKED_V0_CONFIG["sl"])
    v0_trades = v0_signals[v0_signals["action"] != "NO_TRADE"].copy()
    v0_labeled = label_all_signals(v0_trades, m1).dropna(subset=["label"])
    v0_costed = apply_costs(v0_labeled, funding)
    v0_costed["time_utc"] = pd.to_datetime(v0_costed["time_utc"])
    v0_costed["exit_time"] = pd.to_datetime(v0_costed["exit_time"])

    # --- Breakout candidate, UNCHANGED default config ---
    bo_signals = generate_breakout_signals(m15_pool, features, regime)  # all defaults: Donchian20, SL2.0x, TP2R, ADX_MIN=20
    bo_trades = bo_signals[bo_signals["action"] != "NO_TRADE"].copy()
    bo_labeled = label_all_signals(bo_trades, m1).dropna(subset=["label"])
    bo_costed = apply_costs(bo_labeled, funding)
    bo_costed["time_utc"] = pd.to_datetime(bo_costed["time_utc"])
    bo_costed["exit_time"] = pd.to_datetime(bo_costed["exit_time"])

    print("=== V0 baseline (reference) ===")
    summarize("V0_baseline (reference)", v0_costed)
    wfo_folds("V0_baseline (reference)", v0_costed)

    row = summarize("Breakout_Donchian20_ADXmin20_ETH", bo_costed)
    wfo_folds("Breakout_Donchian20_ADXmin20_ETH", bo_costed)

    overlap_stats(v0_costed, bo_costed)

    if row:
        pd.DataFrame([row]).set_index("variant").to_csv("docs/research/artifacts/phase3_breakout_summary.csv")
        print("\nSaved: docs/research/artifacts/phase3_breakout_summary.csv")


if __name__ == "__main__":
    main()
