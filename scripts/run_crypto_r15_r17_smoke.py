"""Exploratory: does R15 (CHoCH) or R17 (FVG) — both FALSIFIED on XAU spot,
see docs/research/GOLD_HANDOFF.md master table — do any better on the ETH/XRP
perps we actually run live? Reuses the exact same signal_fn implementations
from the gold track (src/strategy/gold_r15_choch.py, gold_r17_fvg.py) — they
only touch OHLC/ATR, nothing gold-specific — against ETHUSDT/XRPUSDT m15.

NOT the full sacred-holdout pipeline (only ~3y of crypto data exists, vs.
20y for gold — not enough for a 13y DEV / 7y HOLDOUT split with the same
statistical weight). This is a first-pass smoke/grid on the full available
history with quarterly-fold reporting, same cost model + labeling as
docs/FINDINGS.md's ETH/XRP vetting (funding-aware perp costs, not the gold
spread-only cost model). Treat a "pass" here as "worth a proper plan doc +
holdout", not as a validated edge.

session_filter is OFF by default — the gold HIGH_LIQ_HOURS window (London/
Overlap/NY) is a spot-FX liquidity concept; crypto trades 24/7 and ETH/XRP's
own V0 strategy (docs/FINDINGS.md) carries no session filter, so keeping one
here would silently import an untested assumption.

  PYTHONPATH=. .venv/bin/python -u scripts/run_crypto_r15_r17_smoke.py
"""
import numpy as np
import pandas as pd

from src.labeling.triple_barrier import label_all_signals
from src.backtest.costs import apply_costs
from src.strategy.gold_r15_choch import generate_r15_signals
from src.strategy.gold_r17_fvg import generate_r17_signals

SYMBOLS = ["ETHUSDT", "XRPUSDT"]
EMBARGO = pd.Timedelta(hours=12)

R15_GRID = [
    dict(w=w, k_range=k, tp_r_mult=tp, direction=d, session_filter=False)
    for w in (3, 5, 8) for k in (1.5, 2.5) for tp in (1.0, 1.5) for d in ("both", "long")
]
R17_GRID = [
    dict(k_gap=kg, N=n, tp_r_mult=tp, direction=d, session_filter=False)
    for kg in (0.3, 0.5, 0.8) for n in (10, 20) for tp in (1.0, 1.5) for d in ("both", "long")
]


def load(symbol):
    m15 = pd.read_parquet(f"data/raw/{symbol}_15m.parquet")
    m1 = pd.read_parquet(f"data/raw/{symbol}_1m.parquet")
    funding = pd.read_parquet(f"data/raw/{symbol}_USDT_funding.parquet")
    m1_end = m1["time_utc"].max() - pd.Timedelta(hours=12)  # same trailing-fold trim as research_xrp_vetting
    m15 = m15[m15["time_utc"] <= m1_end].reset_index(drop=True)
    return m15, m1, funding


def evaluate(costed):
    r = costed["net_r_multiple"].dropna().to_numpy()
    if len(r) == 0:
        return {"n": 0}
    wins, losses = r[r > 0], r[r < 0]
    gw, gl = wins.sum(), -losses.sum()
    return {
        "n": len(r),
        "win_rate": (r > 0).mean(),
        "mean_r": r.mean(),
        "profit_factor": gw / gl if gl > 0 else float("inf"),
        "total_r": r.sum(),
    }


def fold_positive_frac(costed):
    ct = costed.dropna(subset=["net_r_multiple"]).sort_values("time_utc")
    if ct.empty:
        return 0.0, 0
    start = ct["time_utc"].min().tz_convert("UTC").to_period("Q").start_time.tz_localize("UTC")
    bounds = pd.date_range(start, ct["time_utc"].max() + pd.Timedelta(days=1), freq="QS", tz="UTC")
    pos, counted = [], 0
    for i in range(len(bounds) - 1):
        m = (ct["time_utc"] >= bounds[i] + EMBARGO) & (ct["time_utc"] < bounds[i + 1] - EMBARGO)
        f = ct[m]
        if len(f) >= 20:
            counted += 1
            pos.append(f["net_r_multiple"].sum() > 0)
    return (np.mean(pos) if pos else 0.0), counted


def run_grid(name, signal_fn, grid, symbol, m15, m1, funding):
    print(f"\n--- {name} on {symbol} ---")
    print(f"{'cfg':<55} | {'n':>5} {'win%':>6} {'meanR':>8} {'PF':>6} {'totR':>8} {'folds+':>7} {'foldsN':>6}")
    best = None
    for cfg in grid:
        sig = signal_fn(m15, **cfg)
        live = sig[sig["action"] != "NO_TRADE"].copy() if not sig.empty else sig
        if live.empty:
            continue
        labeled = label_all_signals(live, m1).dropna(subset=["label"])
        if labeled.empty:
            continue
        costed = apply_costs(labeled, funding)
        e = evaluate(costed)
        fp, fn = fold_positive_frac(costed)
        cfg_str = ",".join(f"{k}={v}" for k, v in cfg.items() if k != "session_filter")
        print(f"{cfg_str:<55} | {e['n']:>5} {e['win_rate']*100:>5.1f} {e['mean_r']:>8.4f} "
              f"{e['profit_factor']:>6.2f} {e['total_r']:>8.1f} {fp*100:>6.0f}% {fn:>6}")
        if best is None or e["profit_factor"] > best[1]["profit_factor"]:
            best = (cfg, e, fp, fn)
    if best:
        cfg, e, fp, fn = best
        print(f"  best cell: {cfg} -> PF={e['profit_factor']:.2f} mean_r={e['mean_r']:.4f} "
              f"n={e['n']} folds+={fp*100:.0f}% ({fn} folds counted)")
    else:
        print("  (no trades in any config)")
    return best


def main():
    for symbol in SYMBOLS:
        m15, m1, funding = load(symbol)
        print(f"\n[{symbol}] m15={len(m15):,} m1={len(m1):,} range={m15['time_utc'].min()}..{m15['time_utc'].max()}")
        run_grid("R15 CHoCH", generate_r15_signals, R15_GRID, symbol, m15, m1, funding)
        run_grid("R17 FVG", generate_r17_signals, R17_GRID, symbol, m15, m1, funding)


if __name__ == "__main__":
    main()
