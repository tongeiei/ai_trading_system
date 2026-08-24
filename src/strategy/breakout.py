"""V0 candidate B: Donchian breakout, trades WITH the regime filter dropped
(breakout logic implies its own trend confirmation) but keeps NEWS_BLACKOUT
hook parity with v0_rules.py.

Same output schema as v0_rules.generate_v0_signals — swappable in compare scripts.
"""
import pandas as pd

DONCHIAN_PERIOD = 20  # bars, M15 -> 5h channel
SL_ATR_MULT = 2.0
TP_R_MULT = 2.0
ADX_MIN = 20.0  # require some directional strength, avoid breakouts in dead chop


def generate_breakout_signals(
    m15: pd.DataFrame,
    features: pd.DataFrame,
    regime: pd.Series,
    sl_atr_mult: float = SL_ATR_MULT,
    tp_r_mult: float = TP_R_MULT,
    donchian_period: int = DONCHIAN_PERIOD,
) -> pd.DataFrame:
    close = m15["close"].reset_index(drop=True)
    high = m15["high"].reset_index(drop=True)
    low = m15["low"].reset_index(drop=True)

    # channel computed on bars BEFORE the current one (shift(1)) — breakout
    # must be measured against a channel that doesn't include the breakout bar itself
    donchian_high = high.rolling(donchian_period).max().shift(1)
    donchian_low = low.rolling(donchian_period).min().shift(1)

    atr = (features["f07_atr_norm"] * close).reset_index(drop=True)
    adx = features["f04_adx14_h1"].reset_index(drop=True)

    long_setup = (close > donchian_high) & (adx > ADX_MIN)
    short_setup = (close < donchian_low) & (adx > ADX_MIN)
    # can't be both — guard against tiny channels where high==low edge case
    short_setup = short_setup & ~long_setup

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
        "regime": regime.reset_index(drop=True),
        "action": action,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "sl_distance": sl_distance,
    })
    out.loc[features["f08_atr_percentile"].reset_index(drop=True).isna(), "action"] = "NO_TRADE"
    out.loc[donchian_high.isna(), "action"] = "NO_TRADE"
    return out
