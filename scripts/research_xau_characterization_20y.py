"""XAU/USD 20-year CHARACTERIZATION (Dukascopy spot, 2006-2026).

Profiles the tape BEFORE any strategy is fitted, so strategy choice is driven
by structure, not by curve-fitting. Uses M15+H1 only (no M1/labels needed).

Questions:
  1. Is the "75% RANGE" seen in the 8.5-month Binance sample representative,
     or a 2026 artifact?  -> regime mix per YEAR.
  2. When does gold actually move?  -> volatility by session and by weekday.
  3. Does gold trend or mean-revert at the bar level?  -> return autocorr
     and same-sign run behaviour per year.
  4. Volatility regime over time (ATR% of price).
"""
import numpy as np
import pandas as pd

from src.features.engine import build_features
from src.regime.rules import classify_regime

pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 40)
pd.set_option("display.float_format", lambda x: f"{x:.3f}" if pd.notna(x) else "n/a")

ADX = 35  # same threshold used elsewhere, for comparability


def load():
    m15 = pd.read_parquet("data/raw/XAUUSD_15m.parquet")
    h1 = pd.read_parquet("data/raw/XAUUSD_1h.parquet")
    return m15, h1


def main():
    print(__doc__)
    m15, h1 = load()
    m15["time_utc"] = pd.to_datetime(m15["time_utc"], utc=True)
    h1["time_utc"] = pd.to_datetime(h1["time_utc"], utc=True)
    print(f"M15 bars: {len(m15):,}  range {m15['time_utc'].min()} -> {m15['time_utc'].max()}")

    print("\nbuilding features (may take ~30s on 500k bars)...")
    feats = build_features(m15, h1)
    regime = classify_regime(feats, adx_threshold=ADX).reset_index(drop=True)

    df = m15.reset_index(drop=True).copy()
    df["regime"] = regime
    df["session"] = feats["session"].reset_index(drop=True)
    df["atr"] = (feats["f07_atr_norm"] * df["close"]).reset_index(drop=True)
    df["atr_pct"] = (df["atr"] / df["close"] * 100).reset_index(drop=True)
    df["ret"] = df["close"].pct_change()
    df["year"] = df["time_utc"].dt.year
    df["dow"] = df["time_utc"].dt.dayofweek  # 0=Mon..6=Sun
    valid = feats["f08_atr_percentile"].reset_index(drop=True).notna()
    df = df[valid].reset_index(drop=True)

    # ---- 1. regime mix per year ----
    print("\n================ 1. REGIME MIX PER YEAR (ADX35 on H1) ================")
    per_year = df.groupby("year").apply(
        lambda g: pd.Series({
            "bars": len(g),
            "TREND_%": (g["regime"] == "TREND").mean() * 100,
            "RANGE_%": (g["regime"] == "RANGE").mean() * 100,
            "atr%_median": g["atr_pct"].median(),
            "ann_ret_%": ((g["close"].iloc[-1] / g["close"].iloc[0]) - 1) * 100,
        }), include_groups=False)
    print(per_year.to_string())
    print(f"\nFULL-SAMPLE regime: TREND={ (df['regime']=='TREND').mean()*100:.1f}%  "
          f"RANGE={(df['regime']=='RANGE').mean()*100:.1f}%")
    print("  (8.5-month Binance sample was TREND=25.2% / RANGE=74.8% — compare above)")

    # ---- 2. volatility by session ----
    print("\n================ 2. VOLATILITY BY SESSION ================")
    sess = df.groupby("session").apply(
        lambda g: pd.Series({
            "bars": len(g),
            "share_%": len(g) / len(df) * 100,
            "abs_ret_bps": g["ret"].abs().mean() * 1e4,
            "atr%_median": g["atr_pct"].median(),
        }), include_groups=False).sort_values("abs_ret_bps", ascending=False)
    print(sess.to_string())

    # ---- 2b. volatility by weekday ----
    print("\n----- volatility by weekday (0=Mon .. 4=Fri) -----")
    wd = df.groupby("dow").apply(
        lambda g: pd.Series({
            "bars": len(g),
            "abs_ret_bps": g["ret"].abs().mean() * 1e4,
        }), include_groups=False)
    print(wd.to_string())

    # ---- 3. bar-level trend vs mean-revert: return autocorrelation ----
    print("\n================ 3. TREND vs MEAN-REVERT (M15 return autocorr lag1) ================")
    print("  positive lag1 autocorr => momentum/trend-friendly;  negative => mean-revert-friendly")
    ac = df.groupby("year").apply(
        lambda g: g["ret"].autocorr(lag=1), include_groups=False)
    ac.name = "ret_autocorr_lag1"
    print(ac.to_string())
    full_ac = df["ret"].autocorr(lag=1)
    print(f"\nFULL-SAMPLE M15 return autocorr(lag1) = {full_ac:.4f}")
    # also H1 to see if signal is stronger at higher TF
    h1v = h1.copy()
    h1v["ret"] = h1v["close"].pct_change()
    print(f"FULL-SAMPLE H1  return autocorr(lag1) = {h1v['ret'].autocorr(lag=1):.4f}")

    print("\n================ INTERPRETATION HINTS ================")
    print("- If RANGE% is high in EVERY year -> gold genuinely ranges at H1/ADX scale,")
    print("  the 8.5mo sample was not a fluke; trend-following will struggle structurally.")
    print("- Sign of return autocorr picks the strategy family objectively:")
    print("    >0 favours momentum/breakout,  <0 favours mean-reversion.")
    print("- Session table tells you WHERE to allow entries (liquidity concentration).")


if __name__ == "__main__":
    main()
