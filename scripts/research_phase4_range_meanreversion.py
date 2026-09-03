"""Phase 4 of docs/research/PLAN_CUSTOM.md — RANGE opportunity research, per
research question 5.

PLAN_CUSTOM: "The current V0 does not trade RANGE. Research whether the
rejected mean-reversion strategy can be improved WITHOUT overfitting.
Possible hypothesis: extreme EMA20/ATR deviation, volatility compression,
failed breakout, reversion confirmation. Do NOT simply optimize entry_z
until backtest profit is maximized. The strategy must survive unseen data."

Tests TWO disciplined hypotheses (not a continuous entry_z sweep):

  A. Baseline — src/strategy/mean_reversion.py UNCHANGED (entry_z=2.0,
     SL=1.5x ATR, TP=1.5R, RANGE regime only). Previously only tested on
     BTC (single-split, PF~0.52, rejected — see docs/FINDINGS.md), never
     independently validated on ETH RANGE specifically.

  B. Reversion-confirmation variant — economically motivated: raw
     extreme-deviation entries risk catching a "falling knife" (price
     keeps extending instead of reverting). Requires the extreme
     deviation to have occurred within the last N=3 bars AND the current
     bar shows contraction back toward EMA20 (confirmation), rather than
     entering on the extreme bar itself.

Volatility-compression and failed-breakout hypotheses are intentionally
NOT run in this pass — see report §14 "next experiments" for why (same
anti-overfitting reasoning as Phase 3's unrun breakout variants).

Same rigor as prior phases: research pool only, full cost model, quarterly
anchored WFO with 12h embargo, bootstrap significance, overlap check
against V0. Does not modify src/strategy/mean_reversion.py or v0_rules.py.
"""
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.mean_reversion import generate_mean_reversion_signals
from src.strategy.v0_rules import generate_v0_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs
from src.backtest.significance import bootstrap_mean_test

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

LOCKED_V0_CONFIG = {"adx": 35, "sl": 2.5}
SL_ATR_MULT = 1.5   # matches mean_reversion.py defaults, held constant across variants
TP_R_MULT = 1.5
ENTRY_Z = 2.0
CONFIRM_WINDOW = 3
SACRED_HOLDOUT_START = pd.Timestamp("2026-07-01", tz="UTC")
EMBARGO = pd.Timedelta(hours=12)


def load_data():
    m15 = pd.read_parquet("data/raw/ETHUSDT_15m.parquet")
    h1 = pd.read_parquet("data/raw/ETHUSDT_1h.parquet")
    m1 = pd.read_parquet("data/raw/ETHUSDT_1m.parquet")
    funding = pd.read_parquet("data/raw/ETHUSDT_USDT_funding.parquet")
    return m15, h1, m1, funding


def build_signals_from_setup(m15, features, regime, long_setup, short_setup):
    import numpy as np
    close = m15["close"].reset_index(drop=True)
    atr = (features["f07_atr_norm"] * close).reset_index(drop=True)
    action = pd.Series("NO_TRADE", index=close.index)
    action[long_setup] = "LONG"
    action[short_setup] = "SHORT"

    sl_distance = (atr * SL_ATR_MULT).clip(lower=atr * 0.8, upper=atr * max(3.0, SL_ATR_MULT * 1.2))
    sl_price = pd.Series(np.nan, index=close.index)
    tp_price = pd.Series(np.nan, index=close.index)
    sl_price[long_setup] = close[long_setup] - sl_distance[long_setup]
    tp_price[long_setup] = close[long_setup] + sl_distance[long_setup] * TP_R_MULT
    sl_price[short_setup] = close[short_setup] + sl_distance[short_setup]
    tp_price[short_setup] = close[short_setup] - sl_distance[short_setup] * TP_R_MULT

    out = pd.DataFrame({
        "time_utc": m15["time_utc"].reset_index(drop=True), "close": close,
        "regime": regime.reset_index(drop=True), "action": action,
        "sl_price": sl_price, "tp_price": tp_price, "sl_distance": sl_distance,
    })
    return out[out["action"] != "NO_TRADE"].reset_index(drop=True)


def variant_B_reversion_confirmation(m15, features, regime):
    dist_z = features["f01_dist_ema20_atr"].reset_index(drop=True)
    regime = regime.reset_index(drop=True)
    range_ok = regime == "RANGE"

    was_extreme_low = (dist_z < -ENTRY_Z)
    was_extreme_high = (dist_z > ENTRY_Z)
    extreme_recently_low = was_extreme_low.rolling(CONFIRM_WINDOW).max().shift(1).fillna(0).astype(bool)
    extreme_recently_high = was_extreme_high.rolling(CONFIRM_WINDOW).max().shift(1).fillna(0).astype(bool)

    prev_dist = dist_z.shift(1)
    contracting_up = dist_z > prev_dist     # moving back toward/through zero from below
    contracting_down = dist_z < prev_dist   # moving back toward/through zero from above

    long_setup = range_ok & extreme_recently_low & (dist_z < -0.5) & contracting_up
    short_setup = range_ok & extreme_recently_high & (dist_z > 0.5) & contracting_down
    return build_signals_from_setup(m15, features, regime, long_setup, short_setup)


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


def overlap_pct(v0_costed, other_costed):
    v0_sorted = sorted(zip(v0_costed["time_utc"], v0_costed["exit_time"]), key=lambda w: w[0])
    other_sorted = sorted(zip(other_costed["time_utc"], other_costed["exit_time"]), key=lambda w: w[0])

    def overlaps(a, b):
        return a[0] < b[1] and b[0] < a[1]

    overlap_count, j = 0, 0
    for o in other_sorted:
        while j < len(v0_sorted) and v0_sorted[j][1] <= o[0]:
            j += 1
        k = j
        while k < len(v0_sorted) and v0_sorted[k][0] < o[1]:
            if overlaps(v0_sorted[k], o):
                overlap_count += 1
                break
            k += 1
    pct = 100 * overlap_count / len(other_sorted) if other_sorted else 0.0
    print(f"Trades whose holding window overlaps a concurrent V0 trade: "
          f"{overlap_count}/{len(other_sorted)} ({pct:.1f}%)")


def main():
    m15, h1, m1, funding = load_data()
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)
    pool_mask = m15["time_utc"] < SACRED_HOLDOUT_START
    m15_pool = m15[pool_mask].reset_index(drop=True)
    h1_pool = h1[h1["time_utc"] < SACRED_HOLDOUT_START].reset_index(drop=True)

    features = build_features(m15_pool, h1_pool)
    regime = classify_regime(features, adx_threshold=LOCKED_V0_CONFIG["adx"])
    range_bar_count = (regime == "RANGE").sum()
    print(f"RANGE regime bars in research pool: {range_bar_count} ({100*range_bar_count/len(regime):.1f}% of pool)\n")

    v0_signals = generate_v0_signals(m15_pool, features, regime, sl_atr_mult=LOCKED_V0_CONFIG["sl"])
    v0_trades = v0_signals[v0_signals["action"] != "NO_TRADE"].copy()
    v0_labeled = label_all_signals(v0_trades, m1).dropna(subset=["label"])
    v0_costed = apply_costs(v0_labeled, funding)
    v0_costed["time_utc"] = pd.to_datetime(v0_costed["time_utc"])
    v0_costed["exit_time"] = pd.to_datetime(v0_costed["exit_time"])

    print("=== V0 baseline (reference) ===")
    summarize("V0_baseline (reference)", v0_costed)
    wfo_folds("V0_baseline (reference)", v0_costed)

    summary_rows = []

    # --- Variant A: existing mean_reversion.py, unchanged ---
    a_signals = generate_mean_reversion_signals(m15_pool, features, regime)
    a_trades = a_signals[a_signals["action"] != "NO_TRADE"].copy()
    a_labeled = label_all_signals(a_trades, m1).dropna(subset=["label"])
    a_costed = apply_costs(a_labeled, funding)
    a_costed["time_utc"] = pd.to_datetime(a_costed["time_utc"])
    a_costed["exit_time"] = pd.to_datetime(a_costed["exit_time"])
    row = summarize("A_meanrev_baseline_entryZ2.0_ETH", a_costed)
    if row:
        summary_rows.append(row)
    wfo_folds("A_meanrev_baseline_entryZ2.0_ETH", a_costed)
    if len(a_costed):
        overlap_pct(v0_costed, a_costed)

    # --- Variant B: reversion-confirmation ---
    b_signals = variant_B_reversion_confirmation(m15_pool, features, regime)
    b_labeled = label_all_signals(b_signals, m1).dropna(subset=["label"])
    b_costed = apply_costs(b_labeled, funding)
    b_costed["time_utc"] = pd.to_datetime(b_costed["time_utc"])
    b_costed["exit_time"] = pd.to_datetime(b_costed["exit_time"])
    row = summarize("B_meanrev_reversion_confirmation_ETH", b_costed)
    if row:
        summary_rows.append(row)
    wfo_folds("B_meanrev_reversion_confirmation_ETH", b_costed)
    if len(b_costed):
        overlap_pct(v0_costed, b_costed)

    print("\n\n================ SUMMARY TABLE (all variants) ================")
    summary_df = pd.DataFrame(summary_rows).set_index("variant")
    print(summary_df.to_string())
    summary_df.to_csv("docs/research/artifacts/phase4_range_summary.csv")
    print("\nSaved: docs/research/artifacts/phase4_range_summary.csv")


if __name__ == "__main__":
    main()
