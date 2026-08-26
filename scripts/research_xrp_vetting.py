"""XRP full ETH-grade vetting — same scrutiny ETH passed in docs/FINDINGS.md.

XRP was the only 2nd-symbol candidate with a positive backtested edge (locked
V0, holdout PF 1.18, expectancy +0.10R, bootstrap p=0.047) but it JUST missed
the WFO consistency bar (7/12 = 58% vs 60%). This script subjects it to the
exact battery ETH went through before it was chosen, so we judge XRP on the
same evidence, not a single number:

  1. Full 3-year anchored quarterly WFO (12 folds, 12h embargo) — fold means,
     which are significant, std across folds.
  2. Holdout (2025+) bootstrap mean test: p-value and 95% CI.
  3. Slippage sensitivity: holdout PF at 1x / 2x / 3x the base 2bps/side.
  4. Per-quarter breakdown within the holdout.
  5. Long vs short split.
  6. Fold-by-fold overlay vs ETH — do XRP's losing quarters coincide with
     ETH's (2023 H2)? Matters for what a 2nd symbol actually adds.

Locked V0 (ADX35/SL2.5), NO tuning. Slippage recomputed PROPORTIONALLY
(the shared cost module's fixed 0.5 USD/side is wrong for low-priced coins).
"""
import numpy as np
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime
from src.strategy.v0_rules import generate_v0_signals
from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs
from src.backtest.significance import bootstrap_mean_test

pd.set_option("display.width", 200)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

LOCKED = {"adx": 35, "sl": 2.5}
HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")
EMBARGO = pd.Timedelta(hours=12)
BASE_SLIP = 0.0002


def build_costed(symbol, slip_frac=BASE_SLIP):
    m15 = pd.read_parquet(f"data/raw/{symbol}_15m.parquet")
    h1 = pd.read_parquet(f"data/raw/{symbol}_1h.parquet")
    m1 = pd.read_parquet(f"data/raw/{symbol}_1m.parquet")
    funding = pd.read_parquet(f"data/raw/{symbol}_USDT_funding.parquet")
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)
    feats = build_features(m15, h1)
    regime = classify_regime(feats, adx_threshold=LOCKED["adx"])
    sig = generate_v0_signals(m15, feats, regime, sl_atr_mult=LOCKED["sl"])
    tr = sig[sig["action"] != "NO_TRADE"].copy()
    lab = label_all_signals(tr, m1).dropna(subset=["label"])
    c = apply_costs(lab, funding)
    slip = 2 * (c["close"] * slip_frac) / c["sl_distance"]
    c["slippage_r"] = slip
    c["net_r_multiple"] = c["r_multiple"] - c["commission_r"] - slip - c["funding_r"]
    c["time_utc"] = pd.to_datetime(c["time_utc"])
    return c


def pf(x):
    gw = x[x > 0].sum(); gl = -x[x < 0].sum()
    return gw / gl if gl > 0 else float("inf")


def fold_table(costed):
    ct = costed.sort_values("time_utc")
    start = ct["time_utc"].min().tz_convert("UTC").to_period("Q").start_time.tz_localize("UTC")
    bounds = pd.date_range(start, ct["time_utc"].max() + pd.Timedelta(days=1), freq="QS", tz="UTC")
    out = {}
    for i in range(len(bounds) - 1):
        m = (ct["time_utc"] >= bounds[i] + EMBARGO) & (ct["time_utc"] < bounds[i + 1] - EMBARGO)
        f = ct[m]
        if len(f) >= 20:
            q = bounds[i].to_period("Q")
            r = f["net_r_multiple"]
            bs = bootstrap_mean_test(r.to_numpy(), n_resamples=3000, seed=1)
            out[str(q)] = {"n": len(f), "mean_r": r.mean(), "p": bs["p_value"]}
    return pd.DataFrame(out).T


def main():
    print(__doc__)
    xrp = build_costed("XRPUSDT")
    eth = build_costed("ETHUSDT")

    # 1. full WFO
    print("\n========== 1. XRP full-history quarterly WFO ==========")
    ft = fold_table(xrp)
    ft["sig"] = ft["p"].apply(lambda p: "***" if p < 0.01 else ("*" if p < 0.05 else ""))
    ft["pos"] = ft["mean_r"] > 0
    print(ft.to_string())
    npos = int(ft["pos"].sum()); nf = len(ft)
    print(f"folds positive: {npos}/{nf} ({npos/nf:.0%})   std across fold means: {ft['mean_r'].std():.3f}")

    # 2. holdout bootstrap
    print("\n========== 2. XRP holdout (2025+) significance ==========")
    h = xrp[xrp["time_utc"] >= HOLDOUT_START]["net_r_multiple"]
    bs = bootstrap_mean_test(h.to_numpy(), n_resamples=10000, seed=1)
    print(f"n={len(h)} mean={h.mean():+.4f}R PF={pf(h):.3f} "
          f"95%CI=[{bs['ci_95_lo']:.4f},{bs['ci_95_hi']:.4f}] p={bs['p_value']:.4f}")

    # 3. slippage sensitivity
    print("\n========== 3. XRP holdout slippage sensitivity ==========")
    for mult in (1, 2, 3):
        cs = build_costed("XRPUSDT", slip_frac=BASE_SLIP * mult)
        hh = cs[cs["time_utc"] >= HOLDOUT_START]["net_r_multiple"]
        print(f"  slippage {mult}x ({BASE_SLIP*mult*1e4:.0f}bps/side): "
              f"holdout PF={pf(hh):.3f} exp={hh.mean():+.4f}R  {'>=1.10 OK' if pf(hh)>=1.10 else 'BELOW 1.10'}")

    # 4. per-quarter holdout
    print("\n========== 4. XRP per-quarter within holdout ==========")
    hd = xrp[xrp["time_utc"] >= HOLDOUT_START].copy()
    hq = hd.groupby(hd["time_utc"].dt.to_period("Q"))["net_r_multiple"].agg(["count", "mean"])
    print(hq.to_string())
    print(f"holdout quarters positive: {(hq['mean']>0).sum()}/{len(hq)}")

    # 5. long/short split (holdout)
    print("\n========== 5. XRP long/short split (holdout) ==========")
    for a in ("LONG", "SHORT"):
        s = hd[hd["action"] == a]["net_r_multiple"]
        if len(s):
            print(f"  {a}: n={len(s)} exp={s.mean():+.4f}R PF={pf(s):.3f}")

    # 6. overlay vs ETH
    print("\n========== 6. XRP vs ETH fold overlay (do they lose together?) ==========")
    fe = fold_table(eth)
    both = pd.DataFrame({"XRP_mean_r": ft["mean_r"], "ETH_mean_r": fe["mean_r"]})
    both["both_positive"] = (both["XRP_mean_r"] > 0) & (both["ETH_mean_r"] > 0)
    both["both_negative"] = (both["XRP_mean_r"] < 0) & (both["ETH_mean_r"] < 0)
    print(both.to_string())
    corr = both[["XRP_mean_r", "ETH_mean_r"]].corr().iloc[0, 1]
    print(f"\nfold-mean correlation XRP-ETH: {corr:+.3f}  "
          f"(high -> XRP adds trades but NOT drawdown diversification)")


if __name__ == "__main__":
    main()
