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

# Per-symbol, each derived from that SYMBOL'S OWN CAL fold (2025-01..2025-06,
# same V0_CONFIG={"adx":35,"sl":2.5}), GROSS r_multiple (i.e. BEFORE
# commission/slippage — those are added back as cost_r below so the UI can
# show "expected move" and "trading cost" as separate, honest line items
# instead of one pre-netted number). Within each symbol's row, all three
# numbers come from the SAME fold — do not mix win_rate from one period/
# symbol with avg_win/loss from another, that produces internally-
# inconsistent (and once, nonsensically negative) EV estimates. Symbols
# must NOT share another symbol's stats even if similar — XRP's V0 setup
# fires in a different regime mix than ETH's (docs/FINDINGS.md 2026-08 XRP
# vetting), so its true win_rate/avg_win/avg_loss genuinely differ. Update
# only by re-running the CAL-fold calc in run_v1_pipeline.py-style code
# (per-symbol) on fresh data; never hand-tune to make a specific signal
# look better — that's the curve-fitting docs/FINDINGS.md warns against.
# Recomputed 2026-08-28 with the current cost model (commit 4545fa4 fixed
# costs.py's slippage from a fixed $0.5/side, calibrated for BTC, to
# proportional 2bps-of-price — the prior ETH numbers were derived before
# that fix and had gone stale; nobody had re-run the CAL fold since, which
# is what this audit caught). Trading Lead decision (docs/research/
# BTC_EDGE_SEARCH.md Round 6): deploy the corrected numbers even though
# full quarterly WFO under the current cost model shows ETH's gross edge
# is much weaker than previously believed (0.038R full-period vs the old
# 0.170R, only 3/13 quarters clearing the 0.15R gate) — the EV gate
# rejecting most ETH signals from here on is the gate working correctly,
# not a bug to route around. Do NOT raise EV_THRESHOLD_R or retune
# V0_CONFIG to force ETH signals back through; that is the exact
# curve-fitting-to-rescue-a-failing-strategy pattern this project's
# discipline exists to prevent. If ETH needs to trade actively again, that
# is a new, separate research question, not a constants fix.
#   ETH/USDT:USDT was {"win_rate": 0.4389, "avg_win_r": 1.6370, "avg_loss_r": 0.9773} (stale, pre-cost-fix)
SYMBOL_STATS = {
    "ETH/USDT:USDT": {"win_rate": 0.4333, "avg_win_r": 1.5496, "avg_loss_r": 1.0547},
    "XRP/USDT:USDT": {"win_rate": 0.4639, "avg_win_r": 1.5309, "avg_loss_r": 0.9985},
}

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


def estimate_ev(symbol: str, entry_price: float, sl_distance: float) -> EVEstimate:
    """entry_price/sl_distance from the current bar (v0_rules always computes
    sl_distance even for NO_TRADE rows, so this can be called for any bar).
    symbol must have its own entry in SYMBOL_STATS — no cross-symbol fallback,
    a missing entry is a config bug that should fail loudly, not silently
    borrow another symbol's stats."""
    stats = SYMBOL_STATS[symbol]
    win_rate, avg_win_r, avg_loss_r = stats["win_rate"], stats["avg_win_r"], stats["avg_loss_r"]

    cost_r = commission_cost_r(sl_distance, entry_price, TAKER_FEE) + slippage_cost_r(sl_distance, entry_price)
    ev_r = win_rate * avg_win_r - (1 - win_rate) * avg_loss_r - cost_r

    # convert R-multiples to a price-relative percentage for display, matching
    # the format requested: "Expected move" and "Trading cost" as % of price
    r_to_pct = sl_distance / entry_price * 100 if entry_price else 0.0

    return EVEstimate(
        win_rate=win_rate,
        avg_win_r=avg_win_r,
        avg_loss_r=avg_loss_r,
        cost_r=cost_r,
        ev_r=ev_r,
        expected_move_pct=ev_r * r_to_pct,
        trading_cost_pct=cost_r * r_to_pct,
        passes_gate=ev_r >= EV_THRESHOLD_R,
    )
