"""Phase 1 of docs/PLAN_CUSTOM.md — regime filter (ADX threshold) sensitivity.

Tests whether the live ADX>35 TREND-regime cutoff is unnecessarily
restrictive, per PLAN_CUSTOM research question 2. Per the Phase 0 funnel
finding, ADX>35 is NOT the primary bottleneck (the EMA20-pullback trigger
is, at -93.4% vs -78.5% for the regime filter) — so this phase specifically
checks whether loosening it recovers pullback-cross bars that were sitting
just outside the TREND window, not just "more TREND bars in general."

Keeps the WINNING entry trigger from Phase 2 (V0's exact single-bar EMA20
cross — every broadened variant underperformed it) and the locked SL/TP —
only the regime classification changes. Does not modify src/regime/rules.py.

Variants:
  V0 baseline : ADX > 35              (live, control)
  A           : ADX > 30
  B           : ADX > 25
  C           : continuous trend score - ADX in the top 30% of its own
                trailing 60-day distribution (rolling percentile > 0.70),
                replacing the fixed absolute cutoff with a relative one so
                the definition of "trending" doesn't drift with the ADX
                level of a given market era.
trend_strength (|EMA50-EMA200|/ATR_H1 > 0.5) is held constant across all
variants — PLAN_CUSTOM's variants are about the ADX side specifically.
"""
import numpy as np
import pandas as pd

from src.features.engine import build_features
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs
from src.backtest.significance import bootstrap_mean_test

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

TREND_STRENGTH_THRESHOLD = 0.5
SL_ATR_MULT = 2.5
TP_R_MULT = 2.0
SACRED_HOLDOUT_START = pd.Timestamp("2026-07-01", tz="UTC")
EMBARGO = pd.Timedelta(hours=12)
ADX_PCTL_WINDOW = 5760  # ~60 days of M15 bars, matches f08_atr_percentile's window


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def load_data():
    m15 = pd.read_parquet("data/raw/ETHUSDT_15m.parquet")
    h1 = pd.read_parquet("data/raw/ETHUSDT_1h.parquet")
    m1 = pd.read_parquet("data/raw/ETHUSDT_1m.parquet")
    funding = pd.read_parquet("data/raw/ETHUSDT_USDT_funding.parquet")
    return m15, h1, m1, funding


def build_common(m15, h1):
    features = build_features(m15, h1)
    close = m15["close"].reset_index(drop=True)
    high = m15["high"].reset_index(drop=True)
    low = m15["low"].reset_index(drop=True)
    ema20 = _ema(close, 20)
    atr = (features["f07_atr_norm"] * close).reset_index(drop=True)
    dist_ema20 = features["f01_dist_ema20_atr"].reset_index(drop=True)
    h1_trend = features["f03_h1_trend_atr"].reset_index(drop=True)
    adx = features["f04_adx14_h1"].reset_index(drop=True)
    adx_pctl = adx.rolling(window=ADX_PCTL_WINDOW, min_periods=200).rank(pct=True)
    trend_strength_ok = h1_trend.abs() > TREND_STRENGTH_THRESHOLD
    atr_pct_valid = features["f08_atr_percentile"].reset_index(drop=True).notna()

    return {
        "time_utc": m15["time_utc"].reset_index(drop=True),
        "close": close, "high": high, "low": low, "atr": atr,
        "dist_ema20": dist_ema20, "h1_trend": h1_trend, "adx": adx, "adx_pctl": adx_pctl,
        "trend_strength_ok": trend_strength_ok, "atr_pct_valid": atr_pct_valid,
    }


def regime_masks(c, adx_threshold=None, adx_pctl_threshold=None):
    """Returns (long_dir, short_dir) — TREND regime AND directional AND warmed-up."""
    if adx_threshold is not None:
        trend_ok = (c["adx"] > adx_threshold) & c["trend_strength_ok"]
    else:
        trend_ok = (c["adx_pctl"] > adx_pctl_threshold) & c["trend_strength_ok"]
    base = trend_ok & c["atr_pct_valid"]
    long_dir = base & (c["h1_trend"] > 0)
    short_dir = base & (c["h1_trend"] < 0)
    return long_dir, short_dir


def ema_cross_trigger(c, long_dir, short_dir):
    """V0's winning entry trigger (Phase 2 control) — exact single-bar cross."""
    prev_dist = c["dist_ema20"].shift(1)
    long_setup = long_dir & (prev_dist <= 0) & (c["dist_ema20"] > 0)
    short_setup = short_dir & (prev_dist >= 0) & (c["dist_ema20"] < 0)
    return long_setup, short_setup


VARIANTS = {
    "V0_baseline_ADX35": lambda c: regime_masks(c, adx_threshold=35.0),
    "A_ADX30": lambda c: regime_masks(c, adx_threshold=30.0),
    "B_ADX25": lambda c: regime_masks(c, adx_threshold=25.0),
    "C_continuous_adx_pctl70": lambda c: regime_masks(c, adx_pctl_threshold=0.70),
}


def build_signals(c, long_setup, short_setup):
    close, atr = c["close"], c["atr"]
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

    regime_col = pd.Series("RANGE", index=close.index)
    regime_col[long_setup | short_setup] = "TREND"

    out = pd.DataFrame({
        "time_utc": c["time_utc"], "close": close, "regime": regime_col,
        "action": action, "sl_price": sl_price, "tp_price": tp_price, "sl_distance": sl_distance,
    })
    return out[out["action"] != "NO_TRADE"].reset_index(drop=True)


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


def main():
    m15, h1, m1, funding = load_data()
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)

    c = build_common(m15, h1)
    pool_mask = c["time_utc"] < SACRED_HOLDOUT_START

    summary_rows = []
    for name, regime_fn in VARIANTS.items():
        long_dir, short_dir = regime_fn(c)
        long_setup, short_setup = ema_cross_trigger(c, long_dir, short_dir)
        long_setup = long_setup & pool_mask
        short_setup = short_setup & pool_mask

        signals = build_signals(c, long_setup, short_setup)
        if len(signals) == 0:
            print(f"\n=== {name}: NO SIGNALS ===")
            continue
        labeled = label_all_signals(signals, m1).dropna(subset=["label"])
        costed = apply_costs(labeled, funding)
        costed["time_utc"] = pd.to_datetime(costed["time_utc"])

        # also report the regime-only funnel stats (before the EMA trigger), for the funnel comparison
        trend_bar_count = int((long_dir | short_dir).sum())
        print(f"\n[{name}] TREND+direction bars (pre-trigger): {trend_bar_count} "
              f"({100*trend_bar_count/pool_mask.sum():.2f}% of pool bars)")

        row = summarize(name, costed)
        if row:
            row["trend_bars"] = trend_bar_count
            summary_rows.append(row)
        wfo_folds(name, costed)

    print("\n\n================ SUMMARY TABLE (all variants) ================")
    summary_df = pd.DataFrame(summary_rows).set_index("variant")
    print(summary_df.to_string())
    summary_df.to_csv("docs/research/artifacts/phase1_adx_summary.csv")
    print("\nSaved: docs/research/artifacts/phase1_adx_summary.csv")


if __name__ == "__main__":
    main()
