"""Cost model for backtest EV — PROJECT_PLAN.md §8, §14.1.

Three cost components applied to every trade:
  1. commission (taker fee, both entry and exit — market orders)
  2. funding (charged every 8h while a position is held, sign depends on
     direction: longs pay when funding_rate > 0, shorts receive)
  3. slippage (placeholder constant until real orderbook depth is collected
     in the mainnet-shadow layer discussed earlier — testnet fills aren't
     trustworthy for this, see PIVOT NOTICE in PROJECT_PLAN.md)

All costs are converted to R-multiples (fractions of sl_distance) so they
subtract directly from the raw r_multiple triple_barrier.py produces.
"""
import pandas as pd

TAKER_FEE = 0.0005          # from config/exchange_spec.yaml — re-read at call time in practice
SLIPPAGE_BPS = 2.0          # slippage per side, in basis points of price (proportional,
                            # so it scales correctly across symbols regardless of price level)


def funding_cost_r(
    entry_time: pd.Timestamp,
    exit_time: pd.Timestamp,
    entry_price: float,
    action: str,
    sl_distance: float,
    funding_rates: pd.DataFrame,
) -> float:
    """Sum funding payments over [entry_time, exit_time), in R-multiples.
    funding_rates: columns [time_utc, funding_rate], one row per 8h funding event.
    A LONG pays when funding_rate > 0 (cost), receives when < 0 (credit) — and
    vice versa for SHORT.
    """
    if pd.isna(exit_time):
        return 0.0
    window = funding_rates[
        (funding_rates["time_utc"] > entry_time) & (funding_rates["time_utc"] <= exit_time)
    ]
    if window.empty:
        return 0.0

    total_funding_rate = window["funding_rate"].sum()
    sign = 1 if action == "LONG" else -1
    cost_price_units = sign * total_funding_rate * entry_price
    return cost_price_units / sl_distance


def commission_cost_r(sl_distance: float, entry_price: float, taker_fee: float = TAKER_FEE) -> float:
    """Round-trip commission (entry + exit, both taker) in R-multiples."""
    cost_price_units = 2 * taker_fee * entry_price
    return cost_price_units / sl_distance


def slippage_cost_r(sl_distance: float, entry_price: float, slippage_bps: float = SLIPPAGE_BPS) -> float:
    """Round-trip slippage (entry + exit) in R-multiples.

    Slippage is proportional to price (a fixed number of basis points per
    side), NOT a fixed USD amount — a fixed-USD model is wildly wrong across
    symbols of different price levels (e.g. a 0.5 USD/side assumption is
    ~0.001 bps on BTC but ~8000 bps on a $0.06 coin).
    """
    per_side = (slippage_bps / 10_000) * entry_price
    return (2 * per_side) / sl_distance


def apply_costs(labeled_trades: pd.DataFrame, funding_rates: pd.DataFrame, taker_fee: float = TAKER_FEE) -> pd.DataFrame:
    """Adds commission_r, funding_r, slippage_r, and net_r_multiple columns."""
    df = labeled_trades.copy()

    df["commission_r"] = df.apply(
        lambda row: commission_cost_r(row["sl_distance"], row["close"], taker_fee), axis=1
    )
    df["slippage_r"] = df.apply(
        lambda row: slippage_cost_r(row["sl_distance"], row["close"]), axis=1
    )
    df["funding_r"] = df.apply(
        lambda row: funding_cost_r(
            row["time_utc"], row["exit_time"], row["close"], row["action"], row["sl_distance"], funding_rates
        ),
        axis=1,
    )

    df["net_r_multiple"] = df["r_multiple"] - df["commission_r"] - df["slippage_r"] - df["funding_r"]
    return df
