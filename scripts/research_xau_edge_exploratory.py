"""XAU (gold perp) EXPLORATORY edge scan — NOT a validated-edge study.

========================= READ THIS FIRST =========================
XAU/USDT:USDT listed on Binance futures on 2025-12-11, so as of the data
pull there are only ~8.5 MONTHS of history (vs 3 years for BTC/ETH).

That is FAR too little for the falsification-grade validation used
elsewhere in this project (quarterly WFO + sacred holdout + "PF>1.10 AND
>=60% of folds positive", which needs ~12 folds). On 8.5 months you get
~2 quarterly folds — the gate is meaningless.

So EVERYTHING here is EXPLORATORY CHARACTERIZATION, not a green light:
  - H0 control carries ZERO selection risk (locked ETH-derived V0 config,
    run untuned on XAU) — it just asks "does trend-following do anything
    on gold at all". A pass here is still NOT tradeable evidence.
  - Pre-registered structural hypotheses (session/weekend) are economically
    motivated and use existing features, NO parameter tuning.
  - Folds are MONTHLY here (to get ~8 instead of ~2), but each fold is tiny
    and noisy. Fold consistency is reported as a WEAK signal only.
  - NO config produced here may be promoted to live trading on this data.
    A real decision needs 2-3+ years, which only time will provide.
===================================================================
"""
import numpy as np
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.mean_reversion import generate_mean_reversion_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs
from src.backtest.significance import bootstrap_mean_test

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

# Locked V0 config — DERIVED FROM ETH, deliberately NOT re-tuned on XAU.
LOCKED_CONFIG = {"adx": 35, "sl": 2.5}
TP_R_MULT = 2.0
EMBARGO = pd.Timedelta(hours=12)
HIGH_LIQ_SESSIONS = {"LONDON", "OVERLAP", "NY"}


def load_xau():
    m15 = pd.read_parquet("data/raw/XAUUSDT_15m.parquet")
    h1 = pd.read_parquet("data/raw/XAUUSDT_1h.parquet")
    m1 = pd.read_parquet("data/raw/XAUUSDT_1m.parquet")
    funding = pd.read_parquet("data/raw/XAUUSDT_USDT_funding.parquet")
    return m15, h1, m1, funding


def daily_direction(h1):
    """Top layer: resample H1 -> Daily, derive a per-day trend direction.
    Direction = +1 when close>EMA20d AND EMA20d rising, -1 when close<EMA20d
    AND EMA20d falling, else 0 (no clear daily bias). Returned as a frame
    keyed by day-close time so it can be as-of joined onto M15 without leak:
    a given M15 bar may only see days that CLOSED strictly before it.
    """
    h = h1.sort_values("time_utc").copy()
    h["time_utc"] = pd.to_datetime(h["time_utc"])
    h = h.set_index("time_utc")
    d = h["close"].resample("1D").last().dropna().to_frame("close")
    d["ema20"] = d["close"].ewm(span=20, adjust=False).mean()
    d["ema20_slope"] = d["ema20"].diff()
    up = (d["close"] > d["ema20"]) & (d["ema20_slope"] > 0)
    dn = (d["close"] < d["ema20"]) & (d["ema20_slope"] < 0)
    d["daily_dir"] = np.where(up, 1, np.where(dn, -1, 0))
    # stamp the day's info at its CLOSE (00:00 UTC next day) so as-of backward
    # join only exposes fully-closed days
    d = d.reset_index()
    d["avail_at"] = d["time_utc"] + pd.Timedelta(days=1)
    return d[["avail_at", "daily_dir"]].rename(columns={"avail_at": "time_utc"})


def build_common(m15, h1):
    features = build_features(m15, h1)
    close = m15["close"].reset_index(drop=True)
    regime = classify_regime(features, adx_threshold=LOCKED_CONFIG["adx"]).reset_index(drop=True)
    dist_ema20 = features["f01_dist_ema20_atr"].reset_index(drop=True)
    h1_trend = features["f03_h1_trend_atr"].reset_index(drop=True)
    atr = (features["f07_atr_norm"] * close).reset_index(drop=True)
    atr_pct_valid = features["f08_atr_percentile"].reset_index(drop=True).notna()
    session = features["session"].reset_index(drop=True)

    trend_ok = (regime == "TREND") & atr_pct_valid
    long_dir = trend_ok & (h1_trend > 0)
    short_dir = trend_ok & (h1_trend < 0)
    prev_dist = dist_ema20.shift(1)
    long_setup = long_dir & (prev_dist <= 0) & (dist_ema20 > 0)
    short_setup = short_dir & (prev_dist >= 0) & (dist_ema20 < 0)

    # Daily top layer, as-of backward join (only fully-closed days visible)
    t = m15["time_utc"].reset_index(drop=True)
    dd = daily_direction(h1)
    left_t = pd.to_datetime(t).dt.tz_convert("UTC").astype("datetime64[ns, UTC]")
    dd["time_utc"] = dd["time_utc"].dt.tz_convert("UTC").astype("datetime64[ns, UTC]")
    daily_dir = pd.merge_asof(
        pd.DataFrame({"time_utc": left_t}),
        dd.sort_values("time_utc"), on="time_utc", direction="backward",
    )["daily_dir"].fillna(0).astype(int)

    return {
        "time_utc": t, "close": close, "atr": atr,
        "regime": regime, "session": session, "daily_dir": daily_dir,
        "long_setup": long_setup, "short_setup": short_setup,
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
    span_days = (costed["time_utc"].max() - costed["time_utc"].min()).days or 1
    n_years = span_days / 365.25
    long_r = costed.loc[costed["action"] == "LONG", "net_r_multiple"]
    short_r = costed.loc[costed["action"] == "SHORT", "net_r_multiple"]
    bs = bootstrap_mean_test(costed["net_r_multiple"].to_numpy(), n_resamples=5000, seed=1)

    # MONTHLY folds (data too short for quarterly). WEAK signal only.
    ct = costed.copy()
    ct["time_utc"] = pd.to_datetime(ct["time_utc"])
    start = ct["time_utc"].min().tz_convert("UTC").to_period("M").start_time.tz_localize("UTC")
    end = ct["time_utc"].max()
    bounds = pd.date_range(start, end + pd.Timedelta(days=1), freq="MS", tz="UTC")
    fold_avgs = []
    for i in range(len(bounds) - 1):
        m = (ct["time_utc"] >= bounds[i] + EMBARGO) & (ct["time_utc"] < bounds[i + 1] - EMBARGO)
        ft = ct[m]
        if len(ft) >= 10:
            fold_avgs.append(ft["net_r_multiple"].mean())
    n_folds = len(fold_avgs)
    n_pos = sum(1 for x in fold_avgs if x > 0)
    pos_pct = n_pos / n_folds if n_folds else 0

    print(f"\n=== {name} ===")
    print(f"n={n}  trades/year(annualized est)={n/n_years:.1f}  win_rate={win_rate:.1%}  "
          f"expectancy={expectancy:.4f}R  PF={pf:.3f}  MaxDD={max_dd:.2f}R")
    print(f"LONG: n={len(long_r)} avg={long_r.mean():.4f}R   SHORT: n={len(short_r)} avg={short_r.mean():.4f}R")
    print(f"Bootstrap: mean={bs['observed_mean']:.4f}, 95% CI=[{bs['ci_95_lo']:.4f}, {bs['ci_95_hi']:.4f}], p={bs['p_value']:.4f}")
    print(f"MONTHLY folds n>=10: {n_folds}, positive: {n_pos} ({pos_pct:.0%})  "
          f"worst={min(fold_avgs) if fold_avgs else float('nan'):.4f}  best={max(fold_avgs) if fold_avgs else float('nan'):.4f}")
    print("  [EXPLORATORY — monthly folds are tiny/noisy; NOT a validation gate]")
    return {"variant": name, "n": n, "trades_per_year_est": n / n_years, "win_rate": win_rate,
            "expectancy_r": expectancy, "pf": pf, "max_dd_r": max_dd,
            "folds_positive_pct": pos_pct, "n_folds": n_folds, "bootstrap_p": bs["p_value"]}


def characterize(m15, c):
    print("\n================ XAU CHARACTERIZATION ================")
    df = m15.copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"])
    df["dow"] = df["time_utc"].dt.dayofweek  # 0=Mon .. 6=Sun
    df["ret"] = df["close"].pct_change()
    weekend = df["dow"].isin([5, 6])
    print(f"Data span: {df['time_utc'].min()} -> {df['time_utc'].max()}  ({(df['time_utc'].max()-df['time_utc'].min()).days} days)")
    print(f"Bars: {len(df)}  weekend bars: {weekend.sum()} ({weekend.mean():.1%})")
    print(f"Weekday |ret| mean: {df.loc[~weekend,'ret'].abs().mean()*1e4:.2f} bps   "
          f"Weekend |ret| mean: {df.loc[weekend,'ret'].abs().mean()*1e4:.2f} bps")
    reg = c["regime"]
    vc = reg.value_counts(normalize=True)
    print(f"Regime mix: " + "  ".join(f"{k}={v:.1%}" for k, v in vc.items()))
    print(f"Setups: LONG={c['long_setup'].sum()}  SHORT={c['short_setup'].sum()}")
    dd = c["daily_dir"]
    print(f"Daily bias distribution (per M15 bar): up={ (dd==1).mean():.1%}  "
          f"down={(dd==-1).mean():.1%}  flat={(dd==0).mean():.1%}")
    ls_up = (c["long_setup"] & (dd == 1)).sum()
    ss_dn = (c["short_setup"] & (dd == -1)).sum()
    print(f"Setups AGREEING with daily: LONG&up={ls_up}/{c['long_setup'].sum()}  "
          f"SHORT&down={ss_dn}/{c['short_setup'].sum()}")


def main():
    print(__doc__)
    m15, h1, m1, funding = load_xau()
    # trim last 12h so triple-barrier has forward M1 bars to resolve labels
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)

    c = build_common(m15, h1)
    print(f"\nXAU EXPLORATORY pool (full history, no holdout — control is untuned): "
          f"{c['time_utc'].min()} -> {c['time_utc'].max()}")
    characterize(m15, c)

    rows = []

    # H0 control — untuned ETH-derived V0 on XAU. Zero selection risk.
    sig0 = build_signals(c, c["long_setup"], c["short_setup"])
    lab0 = label_all_signals(sig0, m1).dropna(subset=["label"])
    cost0 = apply_costs(lab0, funding); cost0["time_utc"] = pd.to_datetime(cost0["time_utc"])
    r = evaluate("H0_XAU_V0_control_untuned", cost0)
    if r: rows.append(r)

    # H1 high-liquidity sessions (gold is heavily London/NY driven)
    sess_ok = c["session"].isin(HIGH_LIQ_SESSIONS)
    sig1 = build_signals(c, c["long_setup"] & sess_ok, c["short_setup"] & sess_ok)
    lab1 = label_all_signals(sig1, m1).dropna(subset=["label"])
    cost1 = apply_costs(lab1, funding); cost1["time_utc"] = pd.to_datetime(cost1["time_utc"])
    r = evaluate("H1_XAU_high_liquidity_sessions", cost1)
    if r: rows.append(r)

    # H2 exclude weekend (underlying spot gold market is closed Sat/Sun;
    # perp keeps trading but on thin, potentially unrepresentative flow)
    ct = c["time_utc"].dt.dayofweek if hasattr(c["time_utc"].dt, "dayofweek") else pd.to_datetime(c["time_utc"]).dt.dayofweek
    weekday_ok = ~ct.isin([5, 6])
    sig2 = build_signals(c, c["long_setup"] & weekday_ok, c["short_setup"] & weekday_ok)
    lab2 = label_all_signals(sig2, m1).dropna(subset=["label"])
    cost2 = apply_costs(lab2, funding); cost2["time_utc"] = pd.to_datetime(cost2["time_utc"])
    r = evaluate("H2_XAU_weekday_only", cost2)
    if r: rows.append(r)

    # H3 Daily top-layer alignment: take a LONG only when the Daily trend is
    # up (daily_dir==1) and a SHORT only when Daily trend is down. Adds the
    # missing top-of-stack the previous scan lacked. NO parameter tuning
    # (EMA20d direction is pre-registered, not searched).
    daily_up = c["daily_dir"] == 1
    daily_dn = c["daily_dir"] == -1
    sig3 = build_signals(c, c["long_setup"] & daily_up, c["short_setup"] & daily_dn)
    lab3 = label_all_signals(sig3, m1).dropna(subset=["label"])
    cost3 = apply_costs(lab3, funding); cost3["time_utc"] = pd.to_datetime(cost3["time_utc"])
    r = evaluate("H3_XAU_daily_aligned", cost3)
    if r: rows.append(r)

    # H4 stack the two structural filters that individually helped:
    # Daily-aligned AND weekday-only.
    sig4 = build_signals(c, c["long_setup"] & daily_up & weekday_ok,
                         c["short_setup"] & daily_dn & weekday_ok)
    lab4 = label_all_signals(sig4, m1).dropna(subset=["label"])
    cost4 = apply_costs(lab4, funding); cost4["time_utc"] = pd.to_datetime(cost4["time_utc"])
    r = evaluate("H4_XAU_daily_aligned_weekday", cost4)
    if r: rows.append(r)

    # ---------------- Path A: MEAN-REVERSION (regime mix is 75% RANGE) --------
    # The trend family (H0-H4) loses because gold ranges. Mean-reversion is the
    # economically-matched family for a range-dominated tape. Uses the EXISTING
    # src/strategy/mean_reversion.py with its DEFAULT params (entry_z=2.0,
    # SL=1.5x, TP=1.5R) — deliberately NO entry_z sweep (phase4's overfit trap).
    features = build_features(m15, h1)
    regime = classify_regime(features, adx_threshold=LOCKED_CONFIG["adx"])

    mr = generate_mean_reversion_signals(m15, features, regime)
    mr = mr[mr["action"] != "NO_TRADE"].reset_index(drop=True)
    labM = label_all_signals(mr, m1).dropna(subset=["label"])
    costM = apply_costs(labM, funding); costM["time_utc"] = pd.to_datetime(costM["time_utc"])
    r = evaluate("M0_XAU_mean_reversion_default", costM)
    if r: rows.append(r)

    # M1: same MR, weekday-only (weekend thin-flow was toxic for trend; check MR)
    mr_dow = pd.to_datetime(mr["time_utc"]).dt.dayofweek
    mr_wd = mr[~mr_dow.isin([5, 6])].reset_index(drop=True)
    labM1 = label_all_signals(mr_wd, m1).dropna(subset=["label"])
    costM1 = apply_costs(labM1, funding); costM1["time_utc"] = pd.to_datetime(costM1["time_utc"])
    r = evaluate("M1_XAU_mean_reversion_weekday", costM1)
    if r: rows.append(r)

    print("\n\n================ SUMMARY (EXPLORATORY — NOT VALIDATED) ================")
    if rows:
        summ = pd.DataFrame(rows).set_index("variant")
        print(summ.to_string())
        import os
        os.makedirs("docs/research/artifacts", exist_ok=True)
        summ.to_csv("docs/research/artifacts/xau_edge_exploratory_summary.csv")
    print("\nREMINDER: 8.5 months of data. Nothing here is tradeable evidence.")
    print("Any positive result is a candidate to REVISIT after >=2yr of data accrues.")


if __name__ == "__main__":
    main()
