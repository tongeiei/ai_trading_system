"""Position sizing from exchange spec — PROJECT_PLAN.md §10 adapted for crypto.

No lot/tick_value dance like MT5; crypto sizing is: risk_amount / sl_distance,
rounded down to stepSize, rejected if below minNotional. That's it.
"""
import math
from dataclasses import dataclass


@dataclass
class ExchangeSpec:
    amount_step: float     # stepSize
    amount_min: float
    min_notional: float    # minimum order value in quote currency


class PositionRejected(Exception):
    """Raised when the computed size can't be placed — caller must NOT round up."""


def compute_position_size(
    equity: float,
    risk_pct: float,
    entry_price: float,
    sl_price: float,
    spec: ExchangeSpec,
) -> float:
    """Returns quantity (base asset units). Raises PositionRejected if unplaceable.

    risk_pct is expressed as a fraction (0.01 = 1%), matching PROJECT_PLAN.md §9.2.
    """
    if risk_pct <= 0 or risk_pct > 0.05:
        raise ValueError(f"risk_pct out of sane bounds: {risk_pct}")

    sl_distance = abs(entry_price - sl_price)
    if sl_distance <= 0:
        raise ValueError("sl_distance must be positive")

    risk_amount = equity * risk_pct
    raw_qty = risk_amount / sl_distance

    # round DOWN to stepSize — rounding up here would silently break risk management
    steps = math.floor(raw_qty / spec.amount_step)
    qty = steps * spec.amount_step

    notional = qty * entry_price

    if qty < spec.amount_min or notional < spec.min_notional:
        raise PositionRejected(
            f"computed qty={qty} (notional={notional:.2f}) below exchange minimum "
            f"(amount_min={spec.amount_min}, min_notional={spec.min_notional}) — "
            f"account too small for this risk_pct/SL distance, do not round up"
        )

    return qty
