"""2nd-symbol screening — locked V0 (ADX35/SL2.5), NO per-symbol tuning.

Goal (per user): find another symbol where the EXISTING V0 trend-pullback
edge transfers (more trade opportunities / capital deployment), not
diversification. So the bar is the same one ETH cleared, applied unchanged.

Discipline against multiple comparisons:
  - Config is LOCKED (the ETH-derived one); we do NOT tune per symbol. Each
    symbol is one test of the same fixed hypothesis, not a search.
  - Candidates were PRE-REGISTERED (fetch_symbol_candidates.py) before any
    result was seen: XRP, DOGE, ADA, LINK, LTC, AVAX.
  - A symbol must clear the SAME gate ETH did: holdout PF>1.10 AND full-
    history quarterly WFO >=60% folds positive AND bootstrap p<0.05 on the
    holdout. Even then it's a CANDIDATE needing the full ETH-grade vetting
    (slippage 1/2/3x, per-quarter consistency) before any live use.
  - Reference rows for ETH (pass) and BTC (near-miss) are included so the
    candidates are judged against a known yardstick, not in a vacuum.
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
CANDIDATES = ["XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "AVAXUSDT"]
REFERENCE = ["ETHUSDT", "BTCUSDT"]  # known pass / near-miss yardsticks


def run_symbol(symbol):
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
    if len(tr) == 0:
        return None
    lab = label_all_signals(tr, m1).dropna(subset=["label"])
    if len(lab) == 0:
        return None
    costed = apply_costs(lab, funding)
    # FIX: src/backtest/costs.py uses a FIXED 0.5 USD/side slippage, calibrated
    # for BTC (~$60k) — nonsensical for low-priced coins (DOGE $0.06 -> ~5900R
    # of "slippage"). Recompute slippage PROPORTIONALLY (2 bps/side of price),
    # which is ~the effective rate ETH was validated at (0.5/$3000 ~= 1.7 bps),
    # so ETH/BTC reference rows stay comparable. Shared module left untouched.
    SLIP_FRAC = 0.0002
    slip_r = 2 * (costed["close"] * SLIP_FRAC) / costed["sl_distance"]
    costed["slippage_r"] = slip_r
    costed["net_r_multiple"] = (
        costed["r_multiple"] - costed["commission_r"] - slip_r - costed["funding_r"]
    )
    costed["time_utc"] = pd.to_datetime(costed["time_utc"])
    return costed


def pf(x):
    gw = x[x > 0].sum(); gl = -x[x < 0].sum()
    return gw / gl if gl > 0 else float("inf")


def wfo_folds(costed):
    ct = costed.sort_values("time_utc")
    start = ct["time_utc"].min().tz_convert("UTC").to_period("Q").start_time.tz_localize("UTC")
    bounds = pd.date_range(start, ct["time_utc"].max() + pd.Timedelta(days=1), freq="QS", tz="UTC")
    fa = []
    for i in range(len(bounds) - 1):
        m = (ct["time_utc"] >= bounds[i] + EMBARGO) & (ct["time_utc"] < bounds[i + 1] - EMBARGO)
        f = ct[m]
        if len(f) >= 20:
            fa.append(f["net_r_multiple"].mean())
    npos = sum(1 for x in fa if x > 0)
    return len(fa), npos, (npos / len(fa) if fa else 0)


def evaluate(symbol, costed, is_ref):
    hold = costed[costed["time_utc"] >= HOLDOUT_START]
    full = costed
    hr = hold["net_r_multiple"]
    h_pf = pf(hr) if len(hr) else float("nan")
    h_avg = hr.mean() if len(hr) else float("nan")
    nf, npos, pos_pct = wfo_folds(full)
    bs = bootstrap_mean_test(hr.to_numpy(), n_resamples=5000, seed=1) if len(hr) >= 20 else None
    p = bs["p_value"] if bs else float("nan")
    gate = (h_pf > 1.10) and (pos_pct >= 0.60) and (not np.isnan(p) and p < 0.05 and h_avg > 0)
    return {"symbol": symbol, "role": "ref" if is_ref else "candidate",
            "hold_n": len(hr), "hold_avg_r": h_avg, "hold_pf": h_pf,
            "wfo_folds": nf, "wfo_pos": npos, "wfo_pos_pct": pos_pct,
            "hold_boot_p": p, "GATE": gate}


def main():
    print(__doc__)
    rows = []
    for sym in REFERENCE + CANDIDATES:
        print(f"running {sym}...")
        try:
            costed = run_symbol(sym)
        except FileNotFoundError as e:
            print(f"  SKIP {sym}: {e}"); continue
        if costed is None:
            print(f"  {sym}: no trades"); continue
        rows.append(evaluate(sym, costed, sym in REFERENCE))

    df = pd.DataFrame(rows).set_index("symbol")
    print("\n================ 2ND-SYMBOL SCREEN ================")
    print(df.to_string())
    passers = df[(df["role"] == "candidate") & (df["GATE"])]
    print("\nCandidates clearing the full ETH-grade gate "
          "(hold PF>1.10 AND WFO>=60% AND holdout bootstrap p<0.05):")
    print("  " + (", ".join(passers.index) if len(passers) else "NONE"))
    import os
    os.makedirs("docs/research/artifacts", exist_ok=True)
    df.to_csv("docs/research/artifacts/second_symbol_screen.csv")
    print("\nReminder: a passer is a CANDIDATE, not a green light. Next step for any")
    print("passer = ETH-grade vetting (slippage 1/2/3x, per-quarter consistency).")


if __name__ == "__main__":
    main()
