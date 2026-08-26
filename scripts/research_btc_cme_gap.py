"""BTC-specific edge: CME weekend GAP-FILL — pre-registered, disciplined.

Economic rationale (genuinely BTC-specific, not a fitted pattern): CME
Bitcoin futures halt over the weekend while the perp trades 24/7. Institutional
flow anchored to the CME price tends to pull the market back toward the Friday
CME close when CME reopens — the well-documented "CME gap fill". ETH/alts lack
an equally dominant regulated-futures anchor, which is why this is tested on
BTC specifically.

This is a days-horizon, event-driven trade, so it uses a bespoke backtest
(NOT the 12h triple-barrier framework, which would time out most gap fills).

Pre-registration (fixed BEFORE seeing results; NO sweeps):
  - Friday CME close proxy: perp price at Fri 21:00 UTC.
  - Entry: Sun 22:00 UTC (CME reopen), nearest 15m bar. entry = p0.
  - "Meaningful gap": |p0 - fri_close| >= 0.5 * ATR (ATR14 on H1 at entry).
    Smaller gaps are noise -> no trade.
  - Direction: FADE toward the fill. gap up -> SHORT, gap down -> LONG.
  - Target: fri_close (the fill). Stop: p0 +/- 1.5*ATR beyond the gap.
  - Max hold: 5 calendar days, else exit at market (timeout).
  - Costs: taker commission + proportional slippage (2bps/side) + perp
    funding over the hold. R-multiple = PnL / initial risk (|entry-stop|).
  - Sacred holdout: entries >= 2026-07-01 reserved; pool is everything before.
  - GATE (same as the project): pool PF>1.10 AND >=60% of yearly buckets
    positive AND bootstrap p<0.05.
"""
import numpy as np
import pandas as pd

from src.backtest.significance import bootstrap_mean_test

pd.set_option("display.width", 200)
pd.set_option("display.float_format", lambda x: f"{x:.4f}" if pd.notna(x) else "n/a")

HOLDOUT_START = pd.Timestamp("2026-07-01", tz="UTC")
GAP_ATR_MIN = 0.5
STOP_ATR = 1.5
MAX_HOLD = pd.Timedelta(days=5)
TAKER = 0.0005
SLIP_FRAC = 0.0002
FUND_8H = 0.0001  # BTC perp funding ~ neutral-ish; use measured-ish flat carry


def load():
    m15 = pd.read_parquet("data/raw/BTCUSDT_15m.parquet")
    h1 = pd.read_parquet("data/raw/BTCUSDT_1h.parquet")
    for d in (m15, h1):
        d["time_utc"] = pd.to_datetime(d["time_utc"], utc=True)
    # ATR14 on H1
    h = h1.copy()
    tr = pd.concat([(h["high"] - h["low"]),
                    (h["high"] - h["close"].shift()).abs(),
                    (h["low"] - h["close"].shift()).abs()], axis=1).max(axis=1)
    h["atr"] = tr.rolling(14).mean()
    return m15, h[["time_utc", "atr"]]


def nearest_bar(m15, t):
    idx = m15["time_utc"].searchsorted(t, side="left")
    if idx >= len(m15):
        return None
    return m15.iloc[idx]


def backtest(m15, atr_h1):
    m15 = m15.sort_values("time_utc").reset_index(drop=True)
    atr_map = pd.merge_asof(m15[["time_utc"]], atr_h1.sort_values("time_utc"),
                            on="time_utc", direction="backward")["atr"]
    m15 = m15.assign(atr=atr_map)
    times = m15["time_utc"]

    # iterate Fridays
    fridays = m15[(times.dt.dayofweek == 4) & (times.dt.hour == 21) & (times.dt.minute == 0)]
    trades = []
    for _, fr in fridays.iterrows():
        fri_close = fr["close"]
        entry_t = fr["time_utc"] + pd.Timedelta(days=2, hours=1)  # Sun 22:00 UTC
        e = nearest_bar(m15, entry_t)
        if e is None or pd.isna(e["atr"]) or e["atr"] <= 0:
            continue
        p0 = e["close"]; atr = e["atr"]
        gap = p0 - fri_close
        if abs(gap) < GAP_ATR_MIN * atr:
            continue
        action = "SHORT" if gap > 0 else "LONG"
        tp = fri_close
        stop = p0 + (STOP_ATR * atr if action == "SHORT" else -STOP_ATR * atr)
        risk = abs(p0 - stop)

        # walk forward on M15 until tp/stop/timeout
        start_idx = m15["time_utc"].searchsorted(e["time_utc"], side="right")
        deadline = e["time_utc"] + MAX_HOLD
        exit_price, exit_reason, exit_t = None, None, None
        for j in range(start_idx, len(m15)):
            bar = m15.iloc[j]
            if bar["time_utc"] > deadline:
                exit_price, exit_reason, exit_t = bar["open"], "timeout", bar["time_utc"]; break
            if action == "SHORT":
                if bar["high"] >= stop:
                    exit_price, exit_reason, exit_t = stop, "stop", bar["time_utc"]; break
                if bar["low"] <= tp:
                    exit_price, exit_reason, exit_t = tp, "fill", bar["time_utc"]; break
            else:
                if bar["low"] <= stop:
                    exit_price, exit_reason, exit_t = stop, "stop", bar["time_utc"]; break
                if bar["high"] >= tp:
                    exit_price, exit_reason, exit_t = tp, "fill", bar["time_utc"]; break
        if exit_price is None:
            continue
        sign = 1 if action == "LONG" else -1
        pnl_price = sign * (exit_price - p0)
        r = pnl_price / risk
        # costs in R
        hold_h = (exit_t - e["time_utc"]) / pd.Timedelta(hours=1)
        comm = 2 * TAKER * p0 / risk
        slip = 2 * (p0 * SLIP_FRAC) / risk
        fund = sign * (FUND_8H * (hold_h / 8)) * p0 / risk  # long pays if funding>0
        net_r = r - comm - slip - fund
        trades.append({"time_utc": e["time_utc"], "action": action, "gap_atr": gap / atr,
                       "exit_reason": exit_reason, "r": r, "net_r": net_r})
    return pd.DataFrame(trades)


def evaluate(name, df):
    if len(df) == 0:
        print(f"\n=== {name}: NO TRADES ==="); return None
    r = df["net_r"]
    win = (r > 0).mean(); exp = r.mean()
    gw = r[r > 0].sum(); gl = -r[r < 0].sum()
    pf = gw / gl if gl > 0 else float("inf")
    fill_rate = (df["exit_reason"] == "fill").mean()
    bs = bootstrap_mean_test(r.to_numpy(), n_resamples=5000, seed=1)
    by_year = r.groupby(df["time_utc"].dt.year).mean()
    pos_years = (by_year > 0).sum(); n_years = by_year.shape[0]
    pos_pct = pos_years / n_years if n_years else 0
    gate = pf > 1.10 and pos_pct >= 0.60 and bs["p_value"] < 0.05 and exp > 0
    print(f"\n=== {name} ===")
    print(f"n={len(df)}  win={win:.1%}  fill_rate={fill_rate:.1%}  exp={exp:.4f}R  PF={pf:.3f}")
    print(f"Bootstrap mean={bs['observed_mean']:.4f} 95%CI=[{bs['ci_95_lo']:.4f},{bs['ci_95_hi']:.4f}] p={bs['p_value']:.4f}")
    print(f"Yearly buckets positive: {pos_years}/{n_years} ({pos_pct:.0%})")
    print("  per-year net_r mean: " + "  ".join(f"{y}={v:+.3f}" for y, v in by_year.items()))
    print(f"GATE (PF>1.10 AND years>=60% AND p<0.05): {'*** PASS ***' if gate else 'FAIL'}")
    return gate


def main():
    print(__doc__)
    m15, atr_h1 = load()
    df = backtest(m15, atr_h1)
    pool = df[df["time_utc"] < HOLDOUT_START]
    hold = df[df["time_utc"] >= HOLDOUT_START]
    print(f"\ntotal gap trades: {len(df)}  pool(<2026-07): {len(pool)}  holdout: {len(hold)}")
    passed = evaluate("BTC_CME_gap_fill_POOL", pool)
    if passed:
        print("\n>>> pool PASSED -> checking sacred holdout:")
        evaluate("BTC_CME_gap_fill_HOLDOUT", hold)
    else:
        print("\nPool failed the gate -> holdout left untouched (protocol).")


if __name__ == "__main__":
    main()
