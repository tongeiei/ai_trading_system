"""Historical-stats EV gate — PROJECT_PLAN.md §8 EV formula, using rule-based
backtest win rate / avg win / avg loss (NOT an ML probability).

We deliberately do NOT label this "AI probability" anywhere — the P5 gate
(docs/FINDINGS.md, run_v1_pipeline.py) showed the LightGBM model scored
AUC ~0.497 on holdout, indistinguishable from noise, and was dropped. What
this module computes is the ETH strategy's own historical base rate,
applied as a real EV gate: if the setup's expected value doesn't clear
trading costs, the signal is downgraded to NO_TRADE even if v0_rules
triggered a candidate.
"""
from dataclasses import dataclass

from src.backtest.costs import commission_cost_r, slippage_cost_r, TAKER_FEE

# Derived from the ETH CAL fold (2025-01..2025-06), GROSS r_multiple (i.e.
# BEFORE commission/slippage — those are added back as cost_r below so the
# UI can show "expected move" and "trading cost" as separate, honest line
# items instead of one pre-netted number). All three numbers come from the
# SAME fold — do not mix win_rate from one period with avg_win/loss from
# another, that produces internally-inconsistent (and once, nonsensically
# negative) EV estimates. Update only by re-running the CAL-fold calc in
# run_v1_pipeline.py-style code on fresh data; never hand-tune to make a
# specific signal look better — that's the curve-fitting docs/FINDINGS.md
# warns against.
HISTORICAL_WIN_RATE = 0.4389
HISTORICAL_AVG_WIN_R = 1.6370
HISTORICAL_AVG_LOSS_R = 0.9773

EV_THRESHOLD_R = 0.15  # §8.2 decision rule: EV < 0.15R -> NO TRADE


@dataclass
class EVEstimate:
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    cost_r: float
    ev_r: float
    expected_move_pct: float
    trading_cost_pct: float
    passes_gate: bool


def estimate_ev(entry_price: float, sl_distance: float) -> EVEstimate:
    """entry_price/sl_distance from the current bar (v0_rules always computes
    sl_distance even for NO_TRADE rows, so this can be called for any bar)."""
    cost_r = commission_cost_r(sl_distance, entry_price, TAKER_FEE) + slippage_cost_r(sl_distance, entry_price)
    ev_r = (HISTORICAL_WIN_RATE * HISTORICAL_AVG_WIN_R
            - (1 - HISTORICAL_WIN_RATE) * HISTORICAL_AVG_LOSS_R
            - cost_r)

    # convert R-multiples to a price-relative percentage for display, matching
    # the format requested: "Expected move" and "Trading cost" as % of price
    r_to_pct = sl_distance / entry_price * 100 if entry_price else 0.0

    return EVEstimate(
        win_rate=HISTORICAL_WIN_RATE,
        avg_win_r=HISTORICAL_AVG_WIN_R,
        avg_loss_r=HISTORICAL_AVG_LOSS_R,
        cost_r=cost_r,
        ev_r=ev_r,
        expected_move_pct=ev_r * r_to_pct,
        trading_cost_pct=cost_r * r_to_pct,
        passes_gate=ev_r >= EV_THRESHOLD_R,
    )
