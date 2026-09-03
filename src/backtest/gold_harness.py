"""Gold (XAU/USD spot) backtest harness — SEPARATE from the ETH/crypto path.

Why a dedicated harness instead of reusing the crypto research scripts:
  * Data is XAU/USD SPOT (Dukascopy, ~20y) not the XAU/USDT perp (~8mo). The
    extra history is the whole point — it supports real quarterly walk-forward
    instead of the "exploratory only" caveat the perp scripts carry.
  * Spot has NO funding rate. Cost = spread + slippage + commission only.
  * Cost assumptions live in config/gold_spec.yaml, not the crypto exchange_spec.

What it REUSES from the existing engine (no forking of core logic):
  * src.features.engine.build_features   — M15 + H1 feature frame
  * src.labeling.triple_barrier          — M1-path triple-barrier labeling
  * src.backtest.significance            — bootstrap mean test

Plug a hypothesis in by writing a `signal_fn` with the SignalFn contract below
(R1 ORB, R8 post-liquidation reversal, ... from docs/research/XAU_REDDIT_SCOUT.md)
and passing it to `run_gold_backtest`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

import numpy as np
import pandas as pd
import yaml

from src.features.engine import build_features
from src.labeling.triple_barrier import label_all_signals
from src.backtest.significance import bootstrap_mean_test

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPEC = REPO_ROOT / "config" / "gold_spec.yaml"


# --------------------------------------------------------------------------- #
# Spec + data loading
# --------------------------------------------------------------------------- #
def load_spec(path: str | Path = DEFAULT_SPEC) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _read(path: str, start=None, end=None) -> pd.DataFrame:
    df = pd.read_parquet(REPO_ROOT / path)
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)
    if start is not None:
        df = df[df["time_utc"] >= pd.Timestamp(start, tz="UTC")]
    if end is not None:
        df = df[df["time_utc"] <= pd.Timestamp(end, tz="UTC")]
    return df.reset_index(drop=True)


def load_gold_data(spec: dict, start=None, end=None):
    """Returns (m15, h1, m1) for XAU/USD spot, optionally sliced to [start, end].

    Slice during development — the full 7.4M-row M1 frame is heavy. `start`/`end`
    accept anything pd.Timestamp understands (e.g. "2020-01-01").
    """
    d = spec["data"]
    m15 = _read(d["m15"], start, end)
    h1 = _read(d["h1"], start, end)
    m1 = _read(d["m1"], start, end)
    return m15, h1, m1


def load_gold_data_all(spec: dict, start=None, end=None) -> dict[str, pd.DataFrame]:
    """Returns {'m1', 'm5', 'm15', 'h1', 'h4'} -> DataFrame for XAU/USD spot,
    optionally sliced to [start, end]. This is the 5-timeframe entry point
    added in P2 (docs/XAU_ARCHITECTURE_AUDIT.md §10) for the data-validation
    pass and future (P3) feature-engine work — `load_gold_data()` above stays
    frozen at its original (m15, h1, m1) 3-tuple contract since it's unpacked
    positionally by every scripts/run_gold_r*.py research script.
    """
    return {k: _read(v, start, end) for k, v in spec["data"].items()}


# --------------------------------------------------------------------------- #
# Signal contract
# --------------------------------------------------------------------------- #
class SignalFn(Protocol):
    """A hypothesis is a callable that turns market data into trade signals.

    Must return a DataFrame with (at least) these columns — the contract
    triple_barrier.label_all_signals + apply_gold_costs expect:
        time_utc     : entry bar-close time (tz-aware UTC)
        close        : entry price
        action       : "LONG" | "SHORT" | "NO_TRADE"
        sl_price     : stop-loss price  (NaN when NO_TRADE)
        tp_price     : take-profit price (NaN when NO_TRADE)
        sl_distance  : abs(entry - sl_price), > 0  (the R unit)

    Rows with action == "NO_TRADE" are dropped before labeling. Any extra
    columns (e.g. "session", "regime") are carried through untouched.
    """

    def __call__(self, m15: pd.DataFrame, h1: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame: ...


SIGNAL_COLUMNS = ["time_utc", "close", "action", "sl_price", "tp_price", "sl_distance"]


# --------------------------------------------------------------------------- #
# Costs — spot gold: spread + slippage + commission, NO funding
# --------------------------------------------------------------------------- #
def apply_gold_costs(labeled: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Adds cost_r and net_r_multiple. Costs are proportional to price (bps),
    converted to R-multiples via sl_distance so they subtract from r_multiple.

    Deliberately NO funding term — spot gold has none. This is the key
    divergence from src.backtest.costs.apply_costs (which is perp-shaped).
    """
    c = spec["costs"]
    bps_round_trip = 2 * (
        c["spread_bps_per_side"] + c["slippage_bps_per_side"] + c["commission_bps_per_side"]
    )
    df = labeled.copy()
    cost_price_units = (bps_round_trip / 1e4) * df["close"]
    df["cost_r"] = cost_price_units / df["sl_distance"]
    df["net_r_multiple"] = df["r_multiple"] - df["cost_r"]
    return df


# --------------------------------------------------------------------------- #
# Metrics + walk-forward gate
# --------------------------------------------------------------------------- #
def evaluate(trades: pd.DataFrame, r_col: str = "net_r_multiple") -> dict:
    """Aggregate performance on a set of labeled+costed trades."""
    r = trades[r_col].dropna().to_numpy()
    if len(r) == 0:
        return {"n": 0}
    wins = r[r > 0]
    losses = r[r < 0]
    gross_win = wins.sum()
    gross_loss = -losses.sum()
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(equity)
    max_dd_r = float((peak - equity).max()) if len(equity) else 0.0
    boot = bootstrap_mean_test(r) if len(r) >= 2 else {}
    return {
        "n": int(len(r)),
        "win_rate": float((r > 0).mean()),
        "mean_r": float(r.mean()),          # == expectancy per trade in R
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "total_r": float(r.sum()),
        "max_dd_r": max_dd_r,
        "sharpe_per_trade": float(r.mean() / r.std()) if r.std() > 0 else float("nan"),
        "boot_ci_lo": boot.get("ci_95_lo"),
        "boot_ci_hi": boot.get("ci_95_hi"),
        "boot_p_value": boot.get("p_value"),
        "boot_significant": boot.get("significant_at_5pct"),
    }


def walk_forward(trades: pd.DataFrame, spec: dict, r_col: str = "net_r_multiple") -> dict:
    """Group trades into out-of-sample folds by entry time and apply the gate.

    NOTE: this is single-config walk-forward *reporting* (does one fixed rule
    hold up across time?). It does NOT re-optimize per fold — parameter search
    with per-fold refit is a separate, stricter step to add per hypothesis.
    """
    v = spec["validation"]
    df = trades.dropna(subset=[r_col]).copy()
    if df.empty:
        return {"folds": [], "n_folds": 0, "gate_pass": False, "reason": "no trades"}
    df["fold"] = df["time_utc"].dt.tz_convert("UTC").dt.tz_localize(None).dt.to_period(v["fold_freq"])

    folds = []
    for period, g in df.groupby("fold"):
        m = evaluate(g, r_col)
        m["fold"] = str(period)
        m["counts_in_gate"] = m["n"] >= v["min_trades_per_fold"]
        folds.append(m)

    counted = [f for f in folds if f["counts_in_gate"]]
    frac_positive = (
        np.mean([f["total_r"] > 0 for f in counted]) if counted else 0.0
    )
    overall = evaluate(df, r_col)
    gate_pass = (
        overall["profit_factor"] >= v["gate_profit_factor"]
        and frac_positive >= v["gate_min_folds_positive"]
        and len(counted) > 0
    )
    return {
        "folds": folds,
        "n_folds": len(folds),
        "n_folds_counted": len(counted),
        "frac_folds_positive": float(frac_positive),
        "overall": overall,
        "gate_pass": bool(gate_pass),
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_gold_backtest(
    signal_fn: SignalFn,
    spec: dict | None = None,
    start=None,
    end=None,
    verbose: bool = True,
) -> dict:
    """Full pipe: load -> features -> signals -> triple-barrier -> costs -> WFO.

    Returns {"trades": DataFrame, "eval": dict, "wfo": dict}.
    """
    spec = spec or load_spec()
    if verbose:
        print(f"[gold] loading {spec['instrument']} data (start={start} end={end}) ...")
    m15, h1, m1 = load_gold_data(spec, start, end)
    if verbose:
        print(f"[gold] m15={len(m15):,} h1={len(h1):,} m1={len(m1):,}")

    features = build_features(m15, h1)
    signals = signal_fn(m15, h1, features)

    missing = [c for c in SIGNAL_COLUMNS if c not in signals.columns]
    if missing:
        raise ValueError(f"signal_fn output missing required columns: {missing}")

    live = signals[signals["action"] != "NO_TRADE"].copy()
    if verbose:
        print(f"[gold] signals: {len(live):,} tradeable of {len(signals):,} bars")
    if live.empty:
        return {"trades": live, "eval": {"n": 0}, "wfo": {"gate_pass": False, "reason": "no signals"}}

    labeled = label_all_signals(live, m1)
    costed = apply_gold_costs(labeled, spec)
    result = {
        "trades": costed,
        "eval": evaluate(costed),
        "wfo": walk_forward(costed, spec),
    }
    if verbose:
        _print_report(result, spec)
    return result


def _print_report(result: dict, spec: dict) -> None:
    e, w = result["eval"], result["wfo"]
    print("\n=== GOLD BACKTEST REPORT ===")
    print(f"trades={e['n']}  win_rate={e.get('win_rate', float('nan')):.3f}  "
          f"mean_r={e.get('mean_r', float('nan')):.4f}  PF={e.get('profit_factor', float('nan')):.3f}")
    print(f"total_r={e.get('total_r', float('nan')):.1f}  max_dd_r={e.get('max_dd_r', float('nan')):.1f}  "
          f"boot_p={e.get('boot_p_value')}")
    print(f"WFO: folds={w['n_folds']} counted={w.get('n_folds_counted')} "
          f"frac_positive={w.get('frac_folds_positive', 0):.2f}  "
          f"GATE={'PASS' if w.get('gate_pass') else 'FAIL'} "
          f"(PF>={spec['validation']['gate_profit_factor']}, "
          f">={spec['validation']['gate_min_folds_positive']:.0%} folds +)")
