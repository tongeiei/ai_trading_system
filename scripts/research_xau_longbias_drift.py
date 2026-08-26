"""XAU long-biased drift-harvest — respecting the ONE real gold edge.

The whole XAU saga concluded: no market-neutral timing alpha exists (trend,
MR, TSMOM all fail vs buy&hold). But buy&hold ITSELF has a real positive
Sharpe (~0.5 over 20yr) — gold drifts up. So the honest "win some / lose
some" strategy is not to fight that with symmetric bets, but to RIDE it and
only step aside in sustained downtrends to cut the worst years (2008-style
-35%, 2013 -28%).

This is classic long-only trend-timing (a la the 200-day-MA rule). It does
NOT try to be clever; it tries to keep most of gold's drift with less
drawdown. Success criterion is HONEST and hard: it must beat plain buy&hold
on RISK-ADJUSTED terms (Sharpe and/or MaxDD), out-of-sample on the 2025-26
holdout too — otherwise "just buy and hold" wins and this machinery is noise.

Variants (canonical MA rules, not tuned):
  L200: long when close > 200d MA, else FLAT
  L100: long when close > 100d MA, else FLAT
  L200s: long when close > 200d MA AND 200d MA rising, else FLAT
Costs: turnover commission+slippage + funding carry while long (perp mean).
"""
import numpy as np
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.float_format", lambda x: f"{x:.3f}" if pd.notna(x) else "n/a")

HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC")
PERP_FUNDING_ANNUAL = 0.0674
ROUNDTRIP_COST = 0.0005 * 2 + 0.0002
TD = 252


def load_daily():
    h1 = pd.read_parquet("data/raw/XAUUSD_1h.parquet")
    h1["time_utc"] = pd.to_datetime(h1["time_utc"], utc=True)
    d = h1.set_index("time_utc")["close"].resample("1D").last().dropna().to_frame("close")
    d["ret"] = d["close"].pct_change()
    return d


def run_rule(d, kind):
    c = d["close"]
    if kind == "L200":
        sig = c > c.rolling(200).mean()
    elif kind == "L100":
        sig = c > c.rolling(100).mean()
    elif kind == "L200s":
        ma = c.rolling(200).mean()
        sig = (c > ma) & (ma.diff() > 0)
    pos = sig.astype(float).shift(1).fillna(0)
    gross = pos * d["ret"]
    cost = pos.diff().abs().fillna(0) * ROUNDTRIP_COST
    funding = pos * (PERP_FUNDING_ANNUAL / TD)
    net = (gross - cost - funding).rename("net")
    return pd.concat([net, pos.rename("pos")], axis=1).dropna()


def stats(net):
    net = net.dropna()
    if len(net) < 30 or net.std() == 0:
        return None
    ann = net.mean() * TD
    vol = net.std() * np.sqrt(TD)
    sharpe = ann / vol
    eq = (1 + net).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    yrs = (net.index.max() - net.index.min()).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    by = net.groupby(net.index.year).sum()
    return {"sharpe": sharpe, "cagr": cagr, "maxdd": dd, "time_in_mkt%": None,
            "pos_years%": (by > 0).mean() * 100}


def main():
    print(__doc__)
    d = load_daily()
    print(f"daily {d.index.min().date()} -> {d.index.max().date()}  n={len(d)}\n")

    def block(net_pos, label):
        pool = net_pos[net_pos.index < HOLDOUT_START]
        hold = net_pos[net_pos.index >= HOLDOUT_START]
        sp = stats(pool["net"]); sh = stats(hold["net"])
        tim = pool["pos"].mean() * 100
        return {"strategy": label, "scope": "POOL(06-24)", "time_in_mkt%": tim, **sp}, \
               ({"strategy": label, "scope": "HOLDOUT(25-26)", "time_in_mkt%": hold["pos"].mean()*100, **sh} if sh else None)

    rows = []
    for kind in ["L200", "L100", "L200s"]:
        np_ = run_rule(d, kind)
        a, b = block(np_, kind)
        rows.append(a)
        if b: rows.append(b)

    # buy & hold as a strategy row (pos=1 always, funding+no turnover)
    bh_net = (d["ret"] - PERP_FUNDING_ANNUAL / TD).rename("net")
    bh = pd.concat([bh_net, pd.Series(1.0, index=d.index, name="pos")], axis=1).dropna()
    a, b = block(bh, "BUY&HOLD(+funding)")
    rows.append(a);  b and rows.append(b)
    # also raw buy&hold with NO funding (spot investor, not perp)
    bh_spot = pd.concat([d["ret"].rename("net"), pd.Series(1.0, index=d.index, name="pos")], axis=1).dropna()
    a, b = block(bh_spot, "BUY&HOLD(spot,no funding)")
    rows.append(a);  b and rows.append(b)

    df = pd.DataFrame(rows).set_index(["strategy", "scope"])
    print(df[["sharpe", "cagr", "maxdd", "pos_years%", "time_in_mkt%"]].to_string())
    print("\nRead: a variant EARNS its keep only if POOL Sharpe or MaxDD clearly")
    print("beats BUY&HOLD, and the edge survives on the untouched HOLDOUT.")


if __name__ == "__main__":
    main()
