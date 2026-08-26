"""XAU/USD MEAN-REVERSION falsification study — 20yr Dukascopy spot.

This is NOT exploratory. With ~20yr (2006-2026) we run the project's real
falsification protocol (same as the ETH/BTC phases in docs/FINDINGS.md):
  - PRE-REGISTERED hypotheses (fixed below BEFORE looking at results), no
    parameter sweeps.
  - Sacred holdout: bars >= 2025-01-01 excluded from all fitting, reserved
    for ONE final check of any survivor. (2025-26 is gold's big bull — the
    exact regime that destroyed naive MR in the 8.5-month scan; a strategy
    that only works pre-2025 must be caught here.)
  - Full cost model: Binance-perp taker fee + slippage + a SYNTHETIC funding
    carry (~6.7%/yr, the measured XAU/USDT perp mean) so spot research still
    reflects the venue we actually trade.
  - Quarterly anchored WFO with 12h embargo, bootstrap significance.
  - GATE: PF > 1.10 AND >= 60% of quarterly folds positive on the research
    pool. Fail -> REJECT, no re-tuning to rescue.

WHY mean-reversion: 20yr characterization shows gold is RANGE ~79% every
single year and M15 return autocorr is negative in ~19/21 years (weakly
mean-reverting). Trend-following was falsified. MR is the structurally
matched family — but its naive form blew up fading the 2025 bull, so the
pre-registered variants add session and higher-TF-trend guards.

CAVEAT still stands: spot XAU/USD feed, not the perp. A survivor must be
re-validated on Binance XAU/USDT microstructure before any live use.

Pre-registered hypotheses:
  R0 (control): mean_reversion.py DEFAULTS untuned (entry_z=2, RANGE-only,
     SL1.5/TP1.5). Zero selection risk; a full 20yr WFO of the already-known
     config is new information at no cost.
  R1: R0 restricted to high-liquidity sessions {OVERLAP, LONDON, NY} — gold
     moves in London-NY (overlap vol ~2x Asia). Structural, no tuning.
  R2: R1 + higher-TF-trend guard: do NOT fade in the direction of the daily
     trend (no long when daily down, no short when daily up) — directly
     targets the "falling knife" that killed naive MR in the 2025 bull.
"""
import numpy as np
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.mean_reversion import generate_mean_reversion_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs
from src.backtest.significance import bootstrap_mean_test

pd.set_option("display.width", 200)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

ADX = 35
SACRED_HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")
EMBARGO = pd.Timedelta(hours=12)
HIGH_LIQ_SESSIONS = {"OVERLAP", "LONDON", "NY"}
PERP_FUNDING_8H = 0.0000625  # measured mean of Binance XAU/USDT funding (~6.7%/yr)


def load():
    m15 = pd.read_parquet("data/raw/XAUUSD_15m.parquet")
    h1 = pd.read_parquet("data/raw/XAUUSD_1h.parquet")
    m1 = pd.read_parquet("data/raw/XAUUSD_1m.parquet")
    for d in (m15, h1, m1):
        d["time_utc"] = pd.to_datetime(d["time_utc"], utc=True)
    return m15, h1, m1


def synthetic_funding(start, end):
    """Flat 8h funding series approximating Binance XAU/USDT perp carry."""
    idx = pd.date_range(start.floor("8h"), end.ceil("8h"), freq="8h", tz="UTC")
    return pd.DataFrame({"time_utc": idx, "funding_rate": PERP_FUNDING_8H})


def daily_dir_series(h1, ref_times):
    """Per-M15-bar daily trend direction via as-of backward join (no leak)."""
    h = h1.sort_values("time_utc").set_index("time_utc")
    d = h["close"].resample("1D").last().dropna().to_frame("close")
    d["ema20"] = d["close"].ewm(span=20, adjust=False).mean()
    d["slope"] = d["ema20"].diff()
    up = (d["close"] > d["ema20"]) & (d["slope"] > 0)
    dn = (d["close"] < d["ema20"]) & (d["slope"] < 0)
    d["daily_dir"] = np.where(up, 1, np.where(dn, -1, 0))
    d = d.reset_index()
    d["avail_at"] = (d["time_utc"] + pd.Timedelta(days=1)).astype("datetime64[ns, UTC]")
    left = pd.DataFrame({"time_utc": pd.to_datetime(ref_times).astype("datetime64[ns, UTC]")})
    merged = pd.merge_asof(left, d[["avail_at", "daily_dir"]].rename(columns={"avail_at": "time_utc"}),
                           on="time_utc", direction="backward")
    return merged["daily_dir"].fillna(0).astype(int)


def max_drawdown_r(net_r):
    eq = net_r.cumsum()
    return (eq - eq.cummax()).min()


def evaluate(name, costed, quarterly=True):
    n = len(costed)
    if n == 0:
        print(f"\n=== {name}: NO TRADES ===")
        return None
    costed = costed.sort_values("exit_time")
    win = (costed["net_r_multiple"] > 0).mean()
    exp = costed["net_r_multiple"].mean()
    gw = costed.loc[costed["net_r_multiple"] > 0, "net_r_multiple"].sum()
    gl = -costed.loc[costed["net_r_multiple"] < 0, "net_r_multiple"].sum()
    pf = gw / gl if gl > 0 else float("inf")
    mdd = max_drawdown_r(costed["net_r_multiple"])
    yrs = ((costed["time_utc"].max() - costed["time_utc"].min()).days or 1) / 365.25
    bs = bootstrap_mean_test(costed["net_r_multiple"].to_numpy(), n_resamples=5000, seed=1)

    ct = costed.copy(); ct["time_utc"] = pd.to_datetime(ct["time_utc"])
    freq = "QS" if quarterly else "MS"
    per = ct["time_utc"].min().tz_convert("UTC").to_period("Q" if quarterly else "M")
    start = per.start_time.tz_localize("UTC")
    bounds = pd.date_range(start, ct["time_utc"].max() + pd.Timedelta(days=1), freq=freq, tz="UTC")
    folds = []
    for i in range(len(bounds) - 1):
        m = (ct["time_utc"] >= bounds[i] + EMBARGO) & (ct["time_utc"] < bounds[i + 1] - EMBARGO)
        f = ct[m]
        if len(f) >= 20:
            folds.append(f["net_r_multiple"].mean())
    nf = len(folds); npos = sum(1 for x in folds if x > 0)
    pos = npos / nf if nf else 0
    gate = pf > 1.10 and pos >= 0.60

    print(f"\n=== {name} ===")
    print(f"n={n}  trades/yr={n/yrs:.0f}  win={win:.1%}  exp={exp:.4f}R  PF={pf:.3f}  MaxDD={mdd:.1f}R")
    print(f"Bootstrap mean={bs['observed_mean']:.4f}  95%CI=[{bs['ci_95_lo']:.4f},{bs['ci_95_hi']:.4f}]  p={bs['p_value']:.4f}")
    print(f"Quarterly folds n>=20: {nf}, positive: {npos} ({pos:.0%})  "
          f"worst={min(folds) if folds else float('nan'):.4f}  best={max(folds) if folds else float('nan'):.4f}")
    print(f"GATE (PF>1.10 AND folds>=60%): {'*** PASS ***' if gate else 'FAIL'}")
    return {"variant": name, "n": n, "trades_per_yr": n / yrs, "win": win, "exp_r": exp,
            "pf": pf, "max_dd_r": mdd, "folds_pos_pct": pos, "n_folds": nf,
            "bootstrap_p": bs["p_value"], "gate_pass": gate}


def build_mr(m15, h1):
    feats = build_features(m15, h1)
    regime = classify_regime(feats, adx_threshold=ADX)
    mr = generate_mean_reversion_signals(m15, feats, regime)
    mr = mr[mr["action"] != "NO_TRADE"].reset_index(drop=True)
    # attach session + daily_dir aligned by time
    sess_map = pd.DataFrame({"time_utc": m15["time_utc"].reset_index(drop=True),
                             "session": feats["session"].reset_index(drop=True)})
    mr = mr.merge(sess_map, on="time_utc", how="left")
    mr["daily_dir"] = daily_dir_series(h1, mr["time_utc"])
    return mr


def run(name, mr_subset, m1, funding, rows):
    lab = label_all_signals(mr_subset, m1).dropna(subset=["label"])
    if len(lab) == 0:
        print(f"\n=== {name}: NO LABELED TRADES ==="); return
    costed = apply_costs(lab, funding); costed["time_utc"] = pd.to_datetime(costed["time_utc"])
    r = evaluate(name, costed)
    if r: rows.append(r)
    return costed


def main():
    print(__doc__)
    m15, h1, m1 = load()

    # trim last 12h so labels can resolve
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)

    print("\nbuilding MR signals over full history...")
    mr_all = build_mr(m15, h1)
    print(f"total MR signals: {len(mr_all)}  "
          f"({mr_all['time_utc'].min()} -> {mr_all['time_utc'].max()})")

    # research pool = before sacred holdout
    pool = mr_all[mr_all["time_utc"] < SACRED_HOLDOUT_START].reset_index(drop=True)
    hold = mr_all[mr_all["time_utc"] >= SACRED_HOLDOUT_START].reset_index(drop=True)
    print(f"research pool: {len(pool)} signals (<2025)   sacred holdout: {len(hold)} signals (>=2025)")

    funding = synthetic_funding(m15["time_utc"].min(), m15["time_utc"].max())
    rows = []

    print("\n############ RESEARCH POOL (2006 - 2024) ############")
    run("R0_MR_default", pool, m1, funding, rows)

    sess_ok = pool["session"].isin(HIGH_LIQ_SESSIONS)
    run("R1_MR_high_liq_sessions", pool[sess_ok].reset_index(drop=True), m1, funding, rows)

    # R2: session + do NOT fade with the daily trend
    guard = (
        ((pool["action"] == "LONG") & (pool["daily_dir"] != -1)) |
        ((pool["action"] == "SHORT") & (pool["daily_dir"] != 1))
    )
    r2_mask = sess_ok & guard
    run("R2_MR_sessions_trendguard", pool[r2_mask].reset_index(drop=True), m1, funding, rows)

    print("\n\n================ POOL SUMMARY (falsification) ================")
    summ = pd.DataFrame(rows).set_index("variant")
    print(summ.to_string())
    import os
    os.makedirs("docs/research/artifacts", exist_ok=True)
    summ.to_csv("docs/research/artifacts/xau_mr_falsification_pool.csv")

    # sacred holdout: only touch it for variants that PASSED the pool gate
    survivors = [r["variant"] for r in rows if r["gate_pass"]]
    print(f"\n############ SACRED HOLDOUT CHECK (2025-2026) ############")
    if not survivors:
        print("No variant passed the pool gate -> holdout stays UNTOUCHED (as protocol demands).")
        print("Conclusion: no price-only MR edge survives 20yr falsification on XAU.")
        return
    print(f"Survivors to check on holdout: {survivors}")
    hrows = []
    if "R0_MR_default" in survivors:
        run("H_R0_holdout", hold, m1, funding, hrows)
    if "R1_MR_high_liq_sessions" in survivors:
        hs = hold[hold["session"].isin(HIGH_LIQ_SESSIONS)].reset_index(drop=True)
        run("H_R1_holdout", hs, m1, funding, hrows)
    if "R2_MR_sessions_trendguard" in survivors:
        hg = (((hold["action"] == "LONG") & (hold["daily_dir"] != -1)) |
              ((hold["action"] == "SHORT") & (hold["daily_dir"] != 1)))
        hs2 = hold[hold["session"].isin(HIGH_LIQ_SESSIONS) & hg].reset_index(drop=True)
        run("H_R2_holdout", hs2, m1, funding, hrows)
    if hrows:
        pd.DataFrame(hrows).set_index("variant").to_csv(
            "docs/research/artifacts/xau_mr_falsification_holdout.csv")


if __name__ == "__main__":
    main()
