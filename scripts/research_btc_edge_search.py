"""BTC-specific edge search — separate from the ETH V1 research program,
per user request ("find a BTC-specific strategy/edge without touching ETH").

DISCIPLINE NOTE (this is the highest false-discovery-risk request in the
project — see docs/FINDINGS.md's warning that ad-hoc re-tuning already
burned several configs on the same data):
  - ETH is NOT touched. This uses BTC data only.
  - Sacred holdout: BTC bars >= 2026-07-01 are excluded from everything
    here, reserved for a single final check of any surviving candidate.
  - A SMALL number of PRE-REGISTERED, economically-motivated hypotheses —
    not a parameter sweep. Every hypothesis and its pass/fail gate is fixed
    BEFORE looking at its result.
  - Gate (same as the crypto screening in FINDINGS.md): PF > 1.10 AND
    >= 60% of WFO folds positive on the research pool. Anything below ->
    REJECT, no re-tuning to rescue it.

Hypotheses:
  H0 (control): V0 locked config on BTC, full multi-fold WFO. FINDINGS.md
     only ran a single train/holdout split on BTC (PF 0.956) — a full WFO
     is genuinely new information, and carries ZERO selection risk (it's
     the already-rejected config, run more thoroughly).
  H1 (session filter): same V0, but entries restricted to high-liquidity
     institutional sessions (LONDON, OVERLAP, NY). Economic rationale: BTC
     is more institutionally driven than ETH; trend signals during
     thin Asia/off hours may be noisier false starts. Structural, uses the
     existing `session` feature, requires NO parameter tuning.
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


def _ema(s, span):
    return s.ewm(span=span, adjust=False).mean()


def load_btc():
    m15 = pd.read_parquet("data/raw/BTCUSDT_15m.parquet")
    h1 = pd.read_parquet("data/raw/BTCUSDT_1h.parquet")
    m1 = pd.read_parquet("data/raw/BTCUSDT_1m.parquet")
    funding = pd.read_parquet("data/raw/BTCUSDT_USDT_funding.parquet")
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
        "regime": regime, "session": session,
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
    n_years = (costed["time_utc"].max() - costed["time_utc"].min()).days / 365.25
    long_r = costed.loc[costed["action"] == "LONG", "net_r_multiple"]
    short_r = costed.loc[costed["action"] == "SHORT", "net_r_multiple"]
    bs = bootstrap_mean_test(costed["net_r_multiple"].to_numpy(), n_resamples=5000, seed=1)

    # WFO folds
    ct = costed.copy()
    ct["time_utc"] = pd.to_datetime(ct["time_utc"])
    start = ct["time_utc"].min().tz_convert("UTC").to_period("Q").start_time.tz_localize("UTC")
    end = ct["time_utc"].max()
    bounds = pd.date_range(start, end + pd.Timedelta(days=1), freq="QS", tz="UTC")
    fold_avgs = []
    for i in range(len(bounds) - 1):
        m = (ct["time_utc"] >= bounds[i] + EMBARGO) & (ct["time_utc"] < bounds[i + 1] - EMBARGO)
        ft = ct[m]
        if len(ft) >= 20:
            fold_avgs.append(ft["net_r_multiple"].mean())
    n_folds = len(fold_avgs)
    n_pos = sum(1 for x in fold_avgs if x > 0)
    pos_pct = n_pos / n_folds if n_folds else 0

    print(f"\n=== {name} ===")
    print(f"n={n}  trades/year={n/n_years:.1f}  win_rate={win_rate:.1%}  expectancy={expectancy:.4f}R  PF={pf:.3f}  MaxDD={max_dd:.2f}R")
    print(f"LONG: n={len(long_r)} avg={long_r.mean():.4f}R   SHORT: n={len(short_r)} avg={short_r.mean():.4f}R")
    print(f"Bootstrap: mean={bs['observed_mean']:.4f}, 95% CI=[{bs['ci_95_lo']:.4f}, {bs['ci_95_hi']:.4f}], p={bs['p_value']:.4f}")
    print(f"WFO folds n>=20: {n_folds}, positive: {n_pos} ({pos_pct:.0%})  worst={min(fold_avgs) if fold_avgs else float('nan'):.4f}  best={max(fold_avgs) if fold_avgs else float('nan'):.4f}")
    gate = pf > 1.10 and pos_pct >= 0.60
    print(f"GATE (PF>1.10 AND folds>=60%): {'*** PASS ***' if gate else 'FAIL'}")
    return {"variant": name, "n": n, "trades_per_year": n / n_years, "win_rate": win_rate,
            "expectancy_r": expectancy, "pf": pf, "max_dd_r": max_dd,
            "folds_positive_pct": pos_pct, "bootstrap_p": bs["p_value"], "gate_pass": gate}


def main():
    m15, h1, m1, funding = load_btc()
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)
    pool = m15["time_utc"] < SACRED_HOLDOUT_START
    m15p = m15[pool].reset_index(drop=True)
    h1p = h1[h1["time_utc"] < SACRED_HOLDOUT_START].reset_index(drop=True)

    c = build_common(m15p, h1p)
    print(f"BTC research pool: {c['time_utc'].min()} -> {c['time_utc'].max()}")

    rows = []

    # H0 control
    sig0 = build_signals(c, c["long_setup"], c["short_setup"])
    lab0 = label_all_signals(sig0, m1).dropna(subset=["label"])
    cost0 = apply_costs(lab0, funding); cost0["time_utc"] = pd.to_datetime(cost0["time_utc"])
    r = evaluate("H0_BTC_V0_control", cost0)
    if r: rows.append(r)

    # H1 session filter
    sess_ok = c["session"].isin(HIGH_LIQ_SESSIONS)
    sig1 = build_signals(c, c["long_setup"] & sess_ok, c["short_setup"] & sess_ok)
    lab1 = label_all_signals(sig1, m1).dropna(subset=["label"])
    cost1 = apply_costs(lab1, funding); cost1["time_utc"] = pd.to_datetime(cost1["time_utc"])
    r = evaluate("H1_BTC_V0_high_liquidity_sessions", cost1)
    if r: rows.append(r)

    print("\n\n================ SUMMARY ================")
    print(pd.DataFrame(rows).set_index("variant").to_string())
    pd.DataFrame(rows).set_index("variant").to_csv("docs/research/artifacts/btc_edge_search_summary.csv")
    print("\nHypotheses tested this run: 2 (1 control + 1 pre-registered). Sacred holdout untouched.")


if __name__ == "__main__":
    main()
