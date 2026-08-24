"""V0 candidate C: mean-reversion — fade extreme distance-from-EMA within
RANGE regime only. Opposite thesis from breakout: bet price snaps back
toward EMA20 after an overextension, but ONLY when the market isn't trending
(regime filter matters more here than for breakout).

Same output schema as v0_rules.generate_v0_signals.
"""
import pandas as pd

ENTRY_Z_THRESHOLD = 2.0   # dist_ema20/atr beyond this = "overextended"
SL_ATR_MULT = 1.5
TP_R_MULT = 1.5           # smaller R:R than trend strategies — reversion targets are the mean, not a runner


def generate_mean_reversion_signals(
    m15: pd.DataFrame,
    features: pd.DataFrame,
    regime: pd.Series,
    sl_atr_mult: float = SL_ATR_MULT,
    tp_r_mult: float = TP_R_MULT,
    entry_z: float = ENTRY_Z_THRESHOLD,
) -> pd.DataFrame:
    close = m15["close"].reset_index(drop=True)
    atr = (features["f07_atr_norm"] * close).reset_index(drop=True)
    dist_z = features["f01_dist_ema20_atr"].reset_index(drop=True)
    regime = regime.reset_index(drop=True)

    # fade: price too far BELOW ema20 in a range -> expect bounce up (LONG)
    #       price too far ABOVE ema20 in a range -> expect pullback down (SHORT)
    long_setup = (regime == "RANGE") & (dist_z < -entry_z)
    short_setup = (regime == "RANGE") & (dist_z > entry_z)

    action = pd.Series("NO_TRADE", index=close.index)
    action[long_setup] = "LONG"
    action[short_setup] = "SHORT"

    sl_distance = (atr * sl_atr_mult).clip(lower=atr * 0.8, upper=atr * max(3.0, sl_atr_mult * 1.2))

    sl_price = pd.Series(float("nan"), index=close.index, dtype="float64")
    tp_price = pd.Series(float("nan"), index=close.index, dtype="float64")
    sl_price[long_setup] = close[long_setup] - sl_distance[long_setup]
    tp_price[long_setup] = close[long_setup] + sl_distance[long_setup] * tp_r_mult
    sl_price[short_setup] = close[short_setup] + sl_distance[short_setup]
    tp_price[short_setup] = close[short_setup] - sl_distance[short_setup] * tp_r_mult

    out = pd.DataFrame({
        "time_utc": m15["time_utc"].reset_index(drop=True),
        "close": close,
        "regime": regime,
        "action": action,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "sl_distance": sl_distance,
    })
    out.loc[features["f08_atr_percentile"].reset_index(drop=True).isna(), "action"] = "NO_TRADE"
    return out
