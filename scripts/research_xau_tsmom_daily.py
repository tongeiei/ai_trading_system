"""XAU daily TIME-SERIES MOMENTUM — the hypothesis the intraday scans missed.

BOLDER, but still disciplined. All prior XAU tests were M15/H1 with a 12h max
hold — a purely intraday bet. That says nothing about multi-week momentum,
which is the DOCUMENTED gold edge (Moskowitz-Ooi-Pedersen TSMOM; gold is a
classic CTA trend instrument held for weeks-to-months). The "79% RANGE at
ADX35/H1" fact does not touch this horizon at all.

This is a position-based (always-in-market) strategy, so it uses a direct
daily equity backtest, NOT the triple-barrier signal framework.

Design (canonical, NOT curve-fitted):
  - Resample H1 -> daily close (2006-2026 spot XAU/USD, Dukascopy).
  - Signal at each day t (using only info through t's close): position =
    sign of trailing K-day return, for the standard academic lookbacks
    K in {21, 63, 126, 252} (~1,3,6,12 months). Held until next day; the
    position updates daily.
  - Long-short (fade both directions) AND long-only variants reported.
  - Costs: commission+slippage on TURNOVER only (position changes), plus a
    daily funding carry = the Binance XAU/USDT perp mean (~6.7%/yr) charged
    on the held notional (longs pay, shorts receive) — conservative for the
    venue we'd actually trade.
  - Sacred holdout: >= 2025-01-01 reported SEPARATELY (out-of-sample).
  - Reported per-lookback and per-year; robustness = consistency across
    BOTH lookbacks and years, not a single tuned number.

Metrics: annualized Sharpe (primary for an always-in strategy), CAGR, max
drawdown, and % of years positive.
"""
import numpy as np
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.float_format", lambda x: f"{x:.3f}" if pd.notna(x) else "n/a")

HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")
LOOKBACKS = {"1m(21d)": 21, "3m(63d)": 63, "6m(126d)": 126, "12m(252d)": 252}
PERP_FUNDING_ANNUAL = 0.0674          # measured Binance XAU/USDT perp mean
ROUNDTRIP_COST = 0.0005 * 2 + 0.0002  # taker both sides + slippage frac (~0.12%)
TRADING_DAYS = 252


def load_daily():
    h1 = pd.read_parquet("data/raw/XAUUSD_1h.parquet")
    h1["time_utc"] = pd.to_datetime(h1["time_utc"], utc=True)
    d = h1.set_index("time_utc")["close"].resample("1D").last().dropna()
    d = d.to_frame("close")
    d["ret"] = d["close"].pct_change()
    return d


def backtest(daily, lookback, long_only):
    d = daily.copy()
    mom = d["close"].pct_change(lookback)
    raw_pos = np.sign(mom)
    if long_only:
        raw_pos = raw_pos.clip(lower=0)
    # trade on next day's return (position set at close of t, earns ret_{t+1})
    pos = raw_pos.shift(1).fillna(0)
    gross = pos * d["ret"]
    # turnover cost when position changes
    turnover = pos.diff().abs().fillna(0)
    cost = turnover * ROUNDTRIP_COST
    # funding carry per day on held notional: long pays, short receives
    funding = pos * (PERP_FUNDING_ANNUAL / TRADING_DAYS)
    net = gross - cost - funding
    out = pd.DataFrame({"net": net, "pos": pos}, index=d.index).dropna()
    return out


def stats(net):
    net = net.dropna()
    if len(net) < 30 or net.std() == 0:
        return None
    ann_ret = net.mean() * TRADING_DAYS
    ann_vol = net.std() * np.sqrt(TRADING_DAYS)
    sharpe = ann_ret / ann_vol if ann_vol else np.nan
    eq = (1 + net).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    yrs = (net.index.max() - net.index.min()).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else np.nan
    by_year = net.groupby(net.index.year).sum()
    pos_years = (by_year > 0).mean()
    return {"ann_ret": ann_ret, "sharpe": sharpe, "cagr": cagr, "maxdd": dd,
            "pos_years%": pos_years * 100, "n_years": by_year.shape[0]}


def main():
    print(__doc__)
    daily = load_daily()
    print(f"daily bars: {len(daily)}  {daily.index.min().date()} -> {daily.index.max().date()}")
    pool = daily[daily.index < HOLDOUT_START]
    hold = daily[daily.index >= HOLDOUT_START]
    print(f"pool (<2025): {len(pool)} days   holdout (>=2025): {len(hold)} days\n")

    for long_only in (False, True):
        tag = "LONG-ONLY" if long_only else "LONG-SHORT"
        print(f"\n################ {tag} ################")
        rows = []
        yearly = {}
        for name, lb in LOOKBACKS.items():
            bt_full = backtest(daily, lb, long_only)
            bt_pool = bt_full[bt_full.index < HOLDOUT_START]["net"]
            bt_hold = bt_full[bt_full.index >= HOLDOUT_START]["net"]
            sp = stats(bt_pool); sh = stats(bt_hold)
            if sp:
                rows.append({"lookback": name, "scope": "POOL(06-24)", **sp})
            if sh:
                rows.append({"lookback": name, "scope": "HOLDOUT(25-26)", **sh})
            yearly[name] = bt_pool.groupby(bt_pool.index.year).sum()
        df = pd.DataFrame(rows).set_index(["lookback", "scope"])
        print(df.to_string())

        # buy & hold benchmark
        bh = daily["ret"].copy()
        bh_pool = bh[bh.index < HOLDOUT_START]; bh_hold = bh[bh.index >= HOLDOUT_START]
        print(f"\nBenchmark buy&hold  POOL: sharpe={stats(bh_pool)['sharpe']:.3f} "
              f"cagr={stats(bh_pool)['cagr']:.3f}   "
              f"HOLDOUT: sharpe={stats(bh_hold)['sharpe']:.3f} cagr={stats(bh_hold)['cagr']:.3f}")

        # per-year net for the best-Sharpe pool lookback
        pool_only = df.xs("POOL(06-24)", level="scope")
        best = pool_only["sharpe"].idxmax()
        print(f"\nPer-year net return — best pool lookback = {best}:")
        print(yearly[best].apply(lambda x: f"{x:+.1%}").to_string())

    print("\n\nNOTE: spot XAU/USD feed; a survivor still needs perp re-validation.")
    print("Sharpe>~0.5 consistent across lookbacks AND positive in most years")
    print("(pool) with the sign holding on the untouched holdout = a real signal.")


if __name__ == "__main__":
    main()
