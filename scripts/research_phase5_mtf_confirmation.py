"""Phase 5 of docs/research/PLAN_CUSTOM.md — multi-timeframe confirmation, research
question 6.

PLAN_CUSTOM lists 4 variants:
  A. M15 only
  B. M15 setup + M5 confirmation
  C. M15 setup + M30 confirmation
  D. H1 regime + M15 setup

Variant D is already what the live V0 baseline does (H1 trend confirmation
+ M15 EMA20-pullback entry — see src/strategy/v0_rules.py) — it is not a
new hypothesis, so this phase reuses the V0 baseline result as D and tests
B and C only: adding a lower-timeframe (M5) or higher-timeframe (M30)
confirmation FILTER on top of the same winning M15 entry trigger (V0's
exact EMA20 cross, unchanged, same as every prior phase's control).

Confirmation rule (fixed, not swept): the most recently CLOSED M5/M30
candle at the moment of the M15 signal must be a bullish candle
(close>open) for a LONG, or bearish (close<open) for a SHORT. M5/M30 bars
are resampled from the same M1 data already used for labeling, and joined
via merge_asof(direction="backward") so only bars fully closed at-or-before
the M15 signal's bar-close time are ever used — no look-ahead.

Goal: determine whether lower/higher-timeframe confirmation increases
valid opportunities or merely adds noise (per PLAN_CUSTOM's exact framing)
— this filter can only REDUCE trade count relative to the M15-only
baseline (it's an AND condition on top of the existing trigger), so the
question here is really "does trading less, but with confirmation,
improve quality enough to be worth it" rather than "does this find more
opportunities."

Does not modify src/strategy/v0_rules.py.
"""
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs
from src.backtest.significance import bootstrap_mean_test

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

LIVE_ADX_THRESHOLD = 35.0
SL_ATR_MULT = 2.5
TP_R_MULT = 2.0
SACRED_HOLDOUT_START = pd.Timestamp("2026-07-01", tz="UTC")
EMBARGO = pd.Timedelta(hours=12)


def load_data():
    m15 = pd.read_parquet("data/raw/ETHUSDT_15m.parquet")
    h1 = pd.read_parquet("data/raw/ETHUSDT_1h.parquet")
    m1 = pd.read_parquet("data/raw/ETHUSDT_1m.parquet")
    funding = pd.read_parquet("data/raw/ETHUSDT_USDT_funding.parquet")
    return m15, h1, m1, funding


def resample_ohlc(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    df = m1.set_index("time_utc").resample(rule, label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    return df.reset_index()


def build_common(m15, h1):
    features = build_features(m15, h1)
    regime = classify_regime(features, adx_threshold=LIVE_ADX_THRESHOLD)
    close = m15["close"].reset_index(drop=True)
    dist_ema20 = features["f01_dist_ema20_atr"].reset_index(drop=True)
    h1_trend = features["f03_h1_trend_atr"].reset_index(drop=True)
    atr = (features["f07_atr_norm"] * close).reset_index(drop=True)
    atr_pct_valid = features["f08_atr_percentile"].reset_index(drop=True).notna()
    regime = regime.reset_index(drop=True)

    trend_ok = (regime == "TREND") & atr_pct_valid
    long_dir = trend_ok & (h1_trend > 0)
    short_dir = trend_ok & (h1_trend < 0)

    prev_dist = dist_ema20.shift(1)
    long_setup = long_dir & (prev_dist <= 0) & (dist_ema20 > 0)
    short_setup = short_dir & (prev_dist >= 0) & (dist_ema20 < 0)

    return {
        "time_utc": m15["time_utc"].reset_index(drop=True), "close": close, "atr": atr,
        "regime": regime, "long_setup": long_setup, "short_setup": short_setup,
    }


def add_mtf_confirmation(c, lower_or_higher_tf: pd.DataFrame):
    """merge_asof each M15 signal bar against the most recent CLOSED bar of
    the confirmation timeframe (backward -> no look-ahead)."""
    sig_times = pd.DataFrame({"time_utc": c["time_utc"]})
    tf = lower_or_higher_tf.sort_values("time_utc")
    joined = pd.merge_asof(sig_times.sort_values("time_utc"), tf, on="time_utc", direction="backward",
                            suffixes=("", "_tf"))
    bullish = joined["close"] > joined["open"]
    bearish = joined["close"] < joined["open"]
    long_confirmed = c["long_setup"] & bullish.values
    short_confirmed = c["short_setup"] & bearish.values
    return long_confirmed, short_confirmed


def build_signals(c, long_setup, short_setup):
    import numpy as np
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

    out = pd.DataFrame({
        "time_utc": c["time_utc"], "close": close, "regime": c["regime"],
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
    bs = bootstrap_mean_test(costed["net_r_multiple"].to_numpy(), n_resamples=5000, seed=1)

    print(f"\n=== {name} ===")
    print(f"n={n}  trades/year={n/n_years:.1f}  win_rate={win_rate:.1%}  "
          f"avg_win={avg_win:.3f}R  avg_loss={avg_loss:.3f}R  expectancy={expectancy:.4f}R  PF={pf:.3f}")
    print(f"MaxDD={max_dd:.2f}R")
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
          f"worst={valid['net_avg_r'].min():.4f}, best={valid['net_avg_r'].max():.4f}")
    return fold_df


def main():
    m15, h1, m1, funding = load_data()
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)
    pool_mask = m15["time_utc"] < SACRED_HOLDOUT_START
    m15_pool = m15[pool_mask].reset_index(drop=True)
    h1_pool = h1[h1["time_utc"] < SACRED_HOLDOUT_START].reset_index(drop=True)
    m1_pool = m1[m1["time_utc"] < SACRED_HOLDOUT_START].reset_index(drop=True)

    print("Resampling M5 and M30 from M1...")
    m5 = resample_ohlc(m1_pool, "5min")
    m30 = resample_ohlc(m1_pool, "30min")
    print(f"M5 bars: {len(m5)}, M30 bars: {len(m30)}\n")

    c = build_common(m15_pool, h1_pool)

    summary_rows = []

    # --- A: M15 only (= V0 baseline, control, reproduced here for a same-run comparison) ---
    a_signals = build_signals(c, c["long_setup"], c["short_setup"])
    a_labeled = label_all_signals(a_signals, m1).dropna(subset=["label"])
    a_costed = apply_costs(a_labeled, funding)
    a_costed["time_utc"] = pd.to_datetime(a_costed["time_utc"])
    row = summarize("A_M15_only (=V0 baseline)", a_costed)
    if row:
        summary_rows.append(row)
    wfo_folds("A_M15_only (=V0 baseline)", a_costed)

    # --- B: M15 + M5 confirmation ---
    long_b, short_b = add_mtf_confirmation(c, m5)
    b_signals = build_signals(c, long_b, short_b)
    b_labeled = label_all_signals(b_signals, m1).dropna(subset=["label"])
    b_costed = apply_costs(b_labeled, funding)
    b_costed["time_utc"] = pd.to_datetime(b_costed["time_utc"])
    row = summarize("B_M15_plus_M5_confirmation", b_costed)
    if row:
        summary_rows.append(row)
    wfo_folds("B_M15_plus_M5_confirmation", b_costed)

    # --- C: M15 + M30 confirmation ---
    long_c, short_c = add_mtf_confirmation(c, m30)
    c_signals = build_signals(c, long_c, short_c)
    c_labeled = label_all_signals(c_signals, m1).dropna(subset=["label"])
    c_costed = apply_costs(c_labeled, funding)
    c_costed["time_utc"] = pd.to_datetime(c_costed["time_utc"])
    row = summarize("C_M15_plus_M30_confirmation", c_costed)
    if row:
        summary_rows.append(row)
    wfo_folds("C_M15_plus_M30_confirmation", c_costed)

    print("\n(D_H1_regime_plus_M15_setup is the existing live V0 architecture itself — not a new variant, see report.)")

    print("\n\n================ SUMMARY TABLE (all variants) ================")
    summary_df = pd.DataFrame(summary_rows).set_index("variant")
    print(summary_df.to_string())
    summary_df.to_csv("docs/research/artifacts/phase5_mtf_summary.csv")
    print("\nSaved: docs/research/artifacts/phase5_mtf_summary.csv")


if __name__ == "__main__":
    main()
