"""V0 rule-based baseline strategy — PROJECT_PLAN.md §3.3.

This is the baseline every future ML version (V1+) must beat. Decisions are
made at bar close only (uses already-shifted features), never intrabar.
"""
import pandas as pd

SL_ATR_MULT = 1.5
TP_R_MULT = 2.0


def generate_v0_signals(
    m15: pd.DataFrame,
    features: pd.DataFrame,
    regime: pd.Series,
    sl_atr_mult: float = SL_ATR_MULT,
    tp_r_mult: float = TP_R_MULT,
    atr_pct_min: float = 0.0,
    atr_pct_max: float = 1.0,
    min_body_ratio: float = 0.0,
) -> pd.DataFrame:
    """Returns one row per M15 bar with action in {LONG, SHORT, NO_TRADE}
    and suggested SL/TP prices when action != NO_TRADE.

    sl_atr_mult/tp_r_mult are exposed as params (not just module constants)
    so cost-sensitivity experiments (e.g. widening SL to dilute commission
    drag, see PROJECT_PLAN.md §8) don't require editing this file each time.

    atr_pct_min/max and min_body_ratio are quality filters per PROJECT_PLAN.md
    §3.3 hard filters (avoid dead/chaotic volatility, avoid indecisive candles).
    """
    close = m15["close"].reset_index(drop=True)
    atr = (features["f07_atr_norm"] * close).reset_index(drop=True)  # de-normalize back to price units

    dist_ema20 = features["f01_dist_ema20_atr"].reset_index(drop=True)
    prev_dist_ema20 = dist_ema20.shift(1)

    regime = regime.reset_index(drop=True)

    long_setup = (
        (regime == "TREND")
        & (features["f03_h1_trend_atr"].reset_index(drop=True) > 0)  # H1 bullish
        & (prev_dist_ema20 <= 0) & (dist_ema20 > 0)  # pullback to EMA20, close back above it
    )
    short_setup = (
        (regime == "TREND")
        & (features["f03_h1_trend_atr"].reset_index(drop=True) < 0)  # H1 bearish
        & (prev_dist_ema20 >= 0) & (dist_ema20 < 0)
    )

    action = pd.Series("NO_TRADE", index=close.index)
    action[long_setup] = "LONG"
    action[short_setup] = "SHORT"

    # quality filters — applied after the base setup, per §3.3 "hard filters"
    atr_pct = features["f08_atr_percentile"].reset_index(drop=True)
    body_ratio = features["f10_candle_body_ratio"].reset_index(drop=True)
    vol_ok = (atr_pct >= atr_pct_min) & (atr_pct <= atr_pct_max)
    body_ok = body_ratio >= min_body_ratio
    action[~(vol_ok & body_ok)] = "NO_TRADE"

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
    # can't act on rows where features aren't warmed up yet
    out.loc[features["f08_atr_percentile"].reset_index(drop=True).isna(), "action"] = "NO_TRADE"
    return out
