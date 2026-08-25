import pytest

from src.live.ev_estimate import estimate_ev, EV_THRESHOLD_R


def test_ev_positive_when_sl_distance_wide_relative_to_price():
    # wide SL (2% of price) dilutes commission/slippage cost in R-terms -> EV clears the gate
    est = estimate_ev(entry_price=60_000, sl_distance=9000)  # 15% SL — wide enough that cost_r is negligible
    assert est.ev_r > EV_THRESHOLD_R
    assert est.passes_gate is True


def test_ev_negative_when_sl_distance_narrow_relative_to_price():
    # narrow SL (0.1% of price) makes cost dominate in R-terms, same
    # commission-drag mechanism found in the original cost-model backtest
    est = estimate_ev(entry_price=60_000, sl_distance=60)
    assert est.passes_gate is False


def test_cost_in_r_terms_shrinks_as_sl_widens():
    # commission/slippage are ~fixed in PRICE terms (taker_fee * price), so as
    # a fraction of a WIDER stop distance (i.e. in R-multiples) they shrink —
    # this is the exact mechanism behind the "widen SL to dilute commission
    # drag" finding from earlier in the project
    narrow = estimate_ev(entry_price=60_000, sl_distance=60)
    wide = estimate_ev(entry_price=60_000, sl_distance=1200)
    assert wide.cost_r < narrow.cost_r


def test_trading_cost_pct_is_roughly_price_invariant_to_sl_width():
    # cost_r ~ 1/sl_distance and expected_move_pct conversion ~ sl_distance,
    # so trading_cost_pct (cost expressed as % of PRICE) stays ~constant
    # regardless of stop width — a real property of fixed-% commission, not a bug
    narrow = estimate_ev(entry_price=60_000, sl_distance=60)
    wide = estimate_ev(entry_price=60_000, sl_distance=1200)
    assert narrow.trading_cost_pct == pytest.approx(wide.trading_cost_pct, rel=1e-9)


def test_win_rate_and_avg_win_loss_are_historical_constants_not_dynamic():
    est1 = estimate_ev(entry_price=60_000, sl_distance=500)
    est2 = estimate_ev(entry_price=2_500, sl_distance=50)
    assert est1.win_rate == est2.win_rate  # same base-rate stats regardless of symbol/price
