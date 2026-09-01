"""BTC — liquidity-sweep / capitulation strategy family (Round 3).

Distinct hypothesis CLASS from Rounds 1-2 (docs/research/BTC_EDGE_SEARCH.md):
Round 1 tested trend/momentum + carry/gap-fill on OHLCV+funding (4
hypotheses, all rejected). Round 2 tested on-chain valuation + vol-regime
(3 hypotheses, all rejected). Neither touched microstructure mechanics —
price sweeping stops/liquidations and reverting. That mechanism has a
stronger economic case on BTC than on gold: BTC perps carry real leverage
and forced liquidations, which is the literal driver these gold strategies
(R8, R11) were built around.

Discipline: reuse the LOCKED gold configs verbatim (src/strategy/
gold_r8_liquidation_reversal.py, gold_r11_wick_fill.py) with NO parameter
tuning for BTC — testing whether the mechanism transfers, not fitting new
thresholds to BTC's history. Session filter kept ON (same high-liquidity
hours as gold/Round-1 H1, which found BTC more institutionally-timed).
Sacred holdout (>= 2026-07-01) stays untouched. Gate: PF > 1.10 AND >= 60%
of WFO folds positive (same as all prior rounds).

Hypotheses:
  H8: R8 liquidation-reversal (capitulation fade) on BTC 15m, locked params.
  H9: R11 wick-fill (imbalance revert) on BTC 15m, locked params.
"""
import pandas as pd

from src.backtest.costs import apply_costs
from src.backtest.significance import bootstrap_mean_test
from src.labeling.triple_barrier import label_all_signals
from src.strategy.gold_r8_liquidation_reversal import generate_r8_signals
from src.strategy.gold_r11_wick_fill import generate_r11_signals

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

SACRED_HOLDOUT_START = pd.Timestamp("2026-07-01", tz="UTC")
EMBARGO = pd.Timedelta(hours=12)


def load_btc():
    m15 = pd.read_parquet("data/raw/BTCUSDT_15m.parquet")
    m1 = pd.read_parquet("data/raw/BTCUSDT_1m.parquet")
    funding = pd.read_parquet("data/raw/BTCUSDT_USDT_funding.parquet")
    return m15, m1, funding


def max_drawdown_r(net_r):
    eq = net_r.cumsum()
    return (eq - eq.cummax()).min()


def evaluate(name, costed):
    n = len(costed)
    if n == 0:
        print(f"\n=== {name}: NO TRADES ===")
        return {"variant": name, "n": 0, "gate_pass": False}
    costed = costed.sort_values("exit_time")
    win_rate = (costed["net_r_multiple"] > 0).mean()
    expectancy = costed["net_r_multiple"].mean()
    gw = costed.loc[costed["net_r_multiple"] > 0, "net_r_multiple"].sum()
    gl = -costed.loc[costed["net_r_multiple"] < 0, "net_r_multiple"].sum()
    pf = gw / gl if gl > 0 else float("inf")
    max_dd = max_drawdown_r(costed["net_r_multiple"])
    n_years = (costed["time_utc"].max() - costed["time_utc"].min()).days / 365.25
    bs = bootstrap_mean_test(costed["net_r_multiple"].to_numpy(), n_resamples=5000, seed=1)

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
    print(f"Bootstrap: mean={bs['observed_mean']:.4f}, 95% CI=[{bs['ci_95_lo']:.4f}, {bs['ci_95_hi']:.4f}], p={bs['p_value']:.4f}")
    print(f"WFO folds n>=20: {n_folds}, positive: {n_pos} ({pos_pct:.0%})")
    gate = pf > 1.10 and pos_pct >= 0.60
    print(f"GATE (PF>1.10 AND folds>=60%): {'*** PASS ***' if gate else 'FAIL'}")
    return {"variant": name, "n": n, "trades_per_year": n / n_years, "win_rate": win_rate,
            "expectancy_r": expectancy, "pf": pf, "max_dd_r": max_dd,
            "folds_positive_pct": pos_pct, "bootstrap_p": bs["p_value"], "gate_pass": gate}


def main():
    m15, m1, funding = load_btc()
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)
    m15p = m15[m15["time_utc"] < SACRED_HOLDOUT_START].reset_index(drop=True)
    print(f"BTC research pool: {m15p['time_utc'].min()} -> {m15p['time_utc'].max()}  ({len(m15p)} bars)")

    rows = []

    sig_r8 = generate_r8_signals(m15p)
    lab_r8 = label_all_signals(sig_r8, m1).dropna(subset=["label"])
    cost_r8 = apply_costs(lab_r8, funding)
    cost_r8["time_utc"] = pd.to_datetime(cost_r8["time_utc"])
    rows.append(evaluate("H8_BTC_R8_liquidation_reversal", cost_r8))

    sig_r11 = generate_r11_signals(m15p)
    lab_r11 = label_all_signals(sig_r11, m1).dropna(subset=["label"])
    cost_r11 = apply_costs(lab_r11, funding)
    cost_r11["time_utc"] = pd.to_datetime(cost_r11["time_utc"])
    rows.append(evaluate("H9_BTC_R11_wick_fill", cost_r11))

    print("\n\n================ SUMMARY ================")
    out = pd.DataFrame(rows).set_index("variant")
    print(out.to_string())
    out.to_csv("docs/research/artifacts/btc_liquidity_family_summary.csv")
    print("\nHypotheses tested this run: 2 (locked gold params, no tuning). Sacred holdout untouched.")


if __name__ == "__main__":
    main()
