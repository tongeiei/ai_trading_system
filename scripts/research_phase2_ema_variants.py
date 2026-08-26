"""Phase 2 of docs/PLAN_CUSTOM.md — EMA20 pullback definition variants.

Tests whether the entry TRIGGER definition (not the regime filter, not
SL/TP, not risk) is too narrow, per the Phase 0 funnel finding that the
EMA20-pullback cross condition removes 93.4% of already-TREND,
already-directional bars — the real bottleneck (see
docs/research/ETH_V1_RESEARCH_REPORT.md).

Every variant below:
  - uses the SAME regime filter (ADX>35, trend-strength>0.5), SAME SL
    (2.5x ATR), SAME TP (2R) as the locked live V0 config — only the
    pullback-trigger definition changes
  - is evaluated only on the RESEARCH POOL (< SACRED_HOLDOUT_START),
    consistent with scripts/research_funnel_diagnosis.py
  - does not import or modify src/strategy/v0_rules.py

V0 baseline is reproduced independently here (not imported) so all
variants share one apples-to-apples signal-construction and labeling
pipeline.
"""
import numpy as np
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs
from src.backtest.significance import bootstrap_mean_test

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

LIVE_ADX_THRESHOLD = 35.0
LIVE_TREND_STRENGTH_THRESHOLD = 0.5
SL_ATR_MULT = 2.5   # locked live value — unchanged across all variants
TP_R_MULT = 2.0      # locked live value — unchanged across all variants
SACRED_HOLDOUT_START = pd.Timestamp("2026-07-01", tz="UTC")
EMBARGO = pd.Timedelta(hours=12)


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def load_data():
    m15 = pd.read_parquet("data/raw/ETHUSDT_15m.parquet")
    h1 = pd.read_parquet("data/raw/ETHUSDT_1h.parquet")
    m1 = pd.read_parquet("data/raw/ETHUSDT_1m.parquet")
    funding = pd.read_parquet("data/raw/ETHUSDT_USDT_funding.parquet")
    # keep enough M1 past the pool boundary to label pool-boundary trades' 12h hold,
    # but never let a signal itself originate at/after the sacred holdout
    return m15, h1, m1, funding


def build_common(m15, h1):
    features = build_features(m15, h1)
    regime = classify_regime(features, adx_threshold=LIVE_ADX_THRESHOLD,
                              trend_strength_threshold=LIVE_TREND_STRENGTH_THRESHOLD)
    close = m15["close"].reset_index(drop=True)
    high = m15["high"].reset_index(drop=True)
    low = m15["low"].reset_index(drop=True)
    ema20 = _ema(close, 20)
    atr = (features["f07_atr_norm"] * close).reset_index(drop=True)
    dist_ema20 = features["f01_dist_ema20_atr"].reset_index(drop=True)  # (close-ema20)/atr
    h1_trend = features["f03_h1_trend_atr"].reset_index(drop=True)
    regime = regime.reset_index(drop=True)
    atr_pct_valid = features["f08_atr_percentile"].reset_index(drop=True).notna()

    trend_ok = regime == "TREND"
    long_dir = trend_ok & (h1_trend > 0) & atr_pct_valid
    short_dir = trend_ok & (h1_trend < 0) & atr_pct_valid

    return {
        "time_utc": m15["time_utc"].reset_index(drop=True),
        "close": close, "high": high, "low": low, "ema20": ema20, "atr": atr,
        "dist_ema20": dist_ema20, "long_dir": long_dir, "short_dir": short_dir,
        "regime": regime,
    }


def variant_V0_baseline(c):
    """Exact single-bar cross — reproduces the LIVE definition independently."""
    prev_dist = c["dist_ema20"].shift(1)
    long_setup = c["long_dir"] & (prev_dist <= 0) & (c["dist_ema20"] > 0)
    short_setup = c["short_dir"] & (prev_dist >= 0) & (c["dist_ema20"] < 0)
    return long_setup, short_setup


def variant_A_touch_then_close_above(c):
    """A/B combined: intrabar low/high pierces EMA20, close reclaims the
    trend side. A ("touch then close above") and B ("low penetrates but
    close remains above") describe the same mechanic given only OHLC bars
    (no sub-bar path) — implemented once, reported once, see report notes."""
    long_setup = c["long_dir"] & (c["low"] <= c["ema20"]) & (c["close"] > c["ema20"])
    short_setup = c["short_dir"] & (c["high"] >= c["ema20"]) & (c["close"] < c["ema20"])
    return long_setup, short_setup


def variant_C_tolerance_band(c, tolerance=0.3):
    """Price enters a fixed +-0.3 ATR band around EMA20 while trending —
    fires on band entry regardless of exact cross bar, single fixed
    tolerance (not swept/optimized)."""
    prev_dist = c["dist_ema20"].shift(1)
    in_band = c["dist_ema20"].abs() <= tolerance
    long_setup = c["long_dir"] & in_band & (c["dist_ema20"] > -tolerance) & (prev_dist <= tolerance) & (c["dist_ema20"] >= prev_dist)
    short_setup = c["short_dir"] & in_band & (c["dist_ema20"] < tolerance) & (prev_dist >= -tolerance) & (c["dist_ema20"] <= prev_dist)
    return long_setup, short_setup


def variant_D_pullback_within_n_bars(c, n=3):
    """Pullback touched EMA20 (or beyond) at any point in the last N bars,
    current bar closes back on the trend-favorable side — broader than V0's
    strict "previous bar only" requirement."""
    touched_long = (c["dist_ema20"] <= 0)
    touched_short = (c["dist_ema20"] >= 0)
    touched_recently_long = touched_long.rolling(n).max().shift(1).fillna(0).astype(bool)
    touched_recently_short = touched_short.rolling(n).max().shift(1).fillna(0).astype(bool)
    long_setup = c["long_dir"] & touched_recently_long & (c["dist_ema20"] > 0)
    short_setup = c["short_dir"] & touched_recently_short & (c["dist_ema20"] < 0)
    return long_setup, short_setup


def variant_E_multibar_momentum(c):
    """Genuine multi-bar pullback (dist shrinking toward EMA20 for 2 bars)
    followed by a momentum-confirmation bar (dist turns back up/down AND
    the bar itself closes in the trend direction) — more selective than V0,
    aims for quality over the raw single-bar-cross trigger."""
    dist = c["dist_ema20"]
    d1, d2 = dist.shift(1), dist.shift(2)
    close = c["close"]
    pullback_long = (d2 > d1) & (d1 <= 1.0) & (d1 > -1.5)   # approaching EMA20 from above, not overextended below
    pullback_short = (d2 < d1) & (d1 >= -1.0) & (d1 < 1.5)
    confirm_long = (dist > d1) & (close > close.shift(1))
    confirm_short = (dist < d1) & (close < close.shift(1))
    long_setup = c["long_dir"] & pullback_long & confirm_long
    short_setup = c["short_dir"] & pullback_short & confirm_short
    return long_setup, short_setup


VARIANTS = {
    "V0_baseline": variant_V0_baseline,
    "A_touch_then_close_above": variant_A_touch_then_close_above,
    "C_tolerance_band_0.3atr": variant_C_tolerance_band,
    "D_pullback_within_3bars": variant_D_pullback_within_n_bars,
    "E_multibar_momentum_confirm": variant_E_multibar_momentum,
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

    out = pd.DataFrame({
        "time_utc": c["time_utc"], "close": close, "regime": c["regime"],
        "action": action, "sl_price": sl_price, "tp_price": tp_price, "sl_distance": sl_distance,
    })
    return out[out["action"] != "NO_TRADE"].reset_index(drop=True)


def max_drawdown_r(net_r_sorted_by_time: pd.Series) -> float:
    equity = net_r_sorted_by_time.cumsum()
    running_peak = equity.cummax()
    dd = equity - running_peak
    return dd.min()  # most negative = worst drawdown, in R units


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
    start = costed["time_utc"].min().to_period("Q").start_time.tz_localize("UTC")
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
    max_entry_time = SACRED_HOLDOUT_START  # no signal may originate at/after this

    summary_rows = []
    for name, fn in VARIANTS.items():
        long_setup, short_setup = fn(c)
        # restrict to research pool BEFORE labeling — never let a signal originate in the sacred holdout
        pool_mask = c["time_utc"] < max_entry_time
        long_setup = long_setup & pool_mask
        short_setup = short_setup & pool_mask

        signals = build_signals(c, long_setup, short_setup)
        if len(signals) == 0:
            print(f"\n=== {name}: NO SIGNALS ===")
            continue
        labeled = label_all_signals(signals, m1).dropna(subset=["label"])
        costed = apply_costs(labeled, funding)
        costed["time_utc"] = pd.to_datetime(costed["time_utc"])

        row = summarize(name, costed)
        if row:
            summary_rows.append(row)
        wfo_folds(name, costed)

    print("\n\n================ SUMMARY TABLE (all variants) ================")
    summary_df = pd.DataFrame(summary_rows).set_index("variant")
    print(summary_df.to_string())
    summary_df.to_csv("data/raw/_phase2_variant_summary.csv")
    print("\nSaved: data/raw/_phase2_variant_summary.csv")


if __name__ == "__main__":
    main()
