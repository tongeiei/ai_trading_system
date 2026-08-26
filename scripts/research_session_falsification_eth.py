"""Session-effect falsification test on ETH — the pre-registered follow-up
from docs/research/BTC_EDGE_SEARCH.md.

The high-liquidity-session filter (LONDON/OVERLAP/NY only) improved every
metric on BTC but still failed the gate. The clean test of whether that is
a REAL market-structure effect vs. noise fitted to BTC's history: does the
SAME filter also improve ETH, where V0 already works?

Pre-registered interpretation (fixed before seeing the result):
  - Session filter IMPROVES ETH (PF, expectancy, fold-consistency all up)
    -> real structural effect, first positive lead in the program, worth a
    single committed holdout test.
  - Session filter HURTS or is neutral on ETH -> the BTC improvement was
    likely noise fitted to BTC; session effect not real; drop it.

ETH V0 locked config is the control and is NOT modified. Research pool only
(< 2026-07-01); ETH sacred holdout untouched.
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

LOCKED_CONFIG = {"adx": 35, "sl": 2.5}
TP_R_MULT = 2.0
SACRED_HOLDOUT_START = pd.Timestamp("2026-07-01", tz="UTC")
EMBARGO = pd.Timedelta(hours=12)
HIGH_LIQ_SESSIONS = {"LONDON", "OVERLAP", "NY"}


def load_eth():
    m15 = pd.read_parquet("data/raw/ETHUSDT_15m.parquet")
    h1 = pd.read_parquet("data/raw/ETHUSDT_1h.parquet")
    m1 = pd.read_parquet("data/raw/ETHUSDT_1m.parquet")
    funding = pd.read_parquet("data/raw/ETHUSDT_USDT_funding.parquet")
    return m15, h1, m1, funding


def build_common(m15, h1):
    features = build_features(m15, h1)
    regime = classify_regime(features, adx_threshold=LOCKED_CONFIG["adx"])
    close = m15["close"].reset_index(drop=True)
    dist_ema20 = features["f01_dist_ema20_atr"].reset_index(drop=True)
    h1_trend = features["f03_h1_trend_atr"].reset_index(drop=True)
    atr = (features["f07_atr_norm"] * close).reset_index(drop=True)
    atr_pct_valid = features["f08_atr_percentile"].reset_index(drop=True).notna()
    session = features["session"].reset_index(drop=True)
    regime = regime.reset_index(drop=True)

    trend_ok = (regime == "TREND") & atr_pct_valid
    long_dir = trend_ok & (h1_trend > 0)
    short_dir = trend_ok & (h1_trend < 0)
    prev_dist = dist_ema20.shift(1)
    long_setup = long_dir & (prev_dist <= 0) & (dist_ema20 > 0)
    short_setup = short_dir & (prev_dist >= 0) & (dist_ema20 < 0)

    return {
        "time_utc": m15["time_utc"].reset_index(drop=True), "close": close, "atr": atr,
        "regime": regime, "session": session, "long_setup": long_setup, "short_setup": short_setup,
    }


def build_signals(c, long_setup, short_setup):
    close, atr = c["close"], c["atr"]
    action = pd.Series("NO_TRADE", index=close.index)
    action[long_setup] = "LONG"
    action[short_setup] = "SHORT"
    sl_distance = (atr * LOCKED_CONFIG["sl"]).clip(lower=atr * 0.8, upper=atr * max(3.0, LOCKED_CONFIG["sl"] * 1.2))
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


def max_drawdown_r(net_r):
    eq = net_r.cumsum()
    return (eq - eq.cummax()).min()


def evaluate(name, costed):
    n = len(costed)
    if n == 0:
        print(f"\n=== {name}: NO TRADES ===")
        return None
    costed = costed.sort_values("exit_time")
    win_rate = (costed["net_r_multiple"] > 0).mean()
    expectancy = costed["net_r_multiple"].mean()
    gw = costed.loc[costed["net_r_multiple"] > 0, "net_r_multiple"].sum()
    gl = -costed.loc[costed["net_r_multiple"] < 0, "net_r_multiple"].sum()
    pf = gw / gl if gl > 0 else float("inf")
    max_dd = max_drawdown_r(costed["net_r_multiple"])
    n_years = (costed["time_utc"].max() - costed["time_utc"].min()).days / 365.25
    bs = bootstrap_mean_test(costed["net_r_multiple"].to_numpy(), n_resamples=5000, seed=1)

    ct = costed.copy(); ct["time_utc"] = pd.to_datetime(ct["time_utc"])
    start = ct["time_utc"].min().tz_convert("UTC").to_period("Q").start_time.tz_localize("UTC")
    end = ct["time_utc"].max()
    bounds = pd.date_range(start, end + pd.Timedelta(days=1), freq="QS", tz="UTC")
    fold_avgs = []
    for i in range(len(bounds) - 1):
        m = (ct["time_utc"] >= bounds[i] + EMBARGO) & (ct["time_utc"] < bounds[i + 1] - EMBARGO)
        ft = ct[m]
        if len(ft) >= 20:
            fold_avgs.append(ft["net_r_multiple"].mean())
    n_folds = len(fold_avgs); n_pos = sum(1 for x in fold_avgs if x > 0)
    pos_pct = n_pos / n_folds if n_folds else 0

    print(f"\n=== {name} ===")
    print(f"n={n}  trades/year={n/n_years:.1f}  win_rate={win_rate:.1%}  expectancy={expectancy:.4f}R  PF={pf:.3f}  MaxDD={max_dd:.2f}R")
    print(f"Bootstrap: mean={bs['observed_mean']:.4f}, 95% CI=[{bs['ci_95_lo']:.4f}, {bs['ci_95_hi']:.4f}], p={bs['p_value']:.4f}")
    print(f"WFO folds n>=20: {n_folds}, positive: {n_pos} ({pos_pct:.0%})  worst={min(fold_avgs):.4f}  best={max(fold_avgs):.4f}")
    return {"variant": name, "n": n, "trades_per_year": n / n_years, "win_rate": win_rate,
            "expectancy_r": expectancy, "pf": pf, "max_dd_r": max_dd, "folds_positive_pct": pos_pct,
            "bootstrap_p": bs["p_value"]}


def main():
    m15, h1, m1, funding = load_eth()
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)
    pool = m15["time_utc"] < SACRED_HOLDOUT_START
    m15p = m15[pool].reset_index(drop=True)
    h1p = h1[h1["time_utc"] < SACRED_HOLDOUT_START].reset_index(drop=True)

    c = build_common(m15p, h1p)
    rows = []

    sig0 = build_signals(c, c["long_setup"], c["short_setup"])
    lab0 = label_all_signals(sig0, m1).dropna(subset=["label"])
    cost0 = apply_costs(lab0, funding); cost0["time_utc"] = pd.to_datetime(cost0["time_utc"])
    r = evaluate("ETH_V0_control", cost0)
    if r: rows.append(r)

    sess_ok = c["session"].isin(HIGH_LIQ_SESSIONS)
    sig1 = build_signals(c, c["long_setup"] & sess_ok, c["short_setup"] & sess_ok)
    lab1 = label_all_signals(sig1, m1).dropna(subset=["label"])
    cost1 = apply_costs(lab1, funding); cost1["time_utc"] = pd.to_datetime(cost1["time_utc"])
    r = evaluate("ETH_V0_high_liquidity_sessions", cost1)
    if r: rows.append(r)

    df = pd.DataFrame(rows).set_index("variant")
    print("\n\n================ ETH SESSION FALSIFICATION SUMMARY ================")
    print(df.to_string())

    # verdict
    ctrl, sess = rows[0], rows[1]
    improved = (sess["pf"] > ctrl["pf"] and sess["expectancy_r"] > ctrl["expectancy_r"]
                and sess["folds_positive_pct"] >= ctrl["folds_positive_pct"])
    print("\n--- PRE-REGISTERED VERDICT ---")
    print(f"PF: {ctrl['pf']:.3f} -> {sess['pf']:.3f}  |  "
          f"expectancy: {ctrl['expectancy_r']:.4f} -> {sess['expectancy_r']:.4f}  |  "
          f"folds+: {ctrl['folds_positive_pct']:.0%} -> {sess['folds_positive_pct']:.0%}")
    if improved:
        print("=> Session filter IMPROVES ETH on all three -> REAL structural effect (positive lead).")
    else:
        print("=> Session filter does NOT coherently improve ETH -> BTC gain was likely noise; drop the hypothesis.")

    df.to_csv("docs/research/artifacts/eth_session_falsification_summary.csv")


if __name__ == "__main__":
    main()
