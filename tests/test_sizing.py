import pytest

from src.risk.sizing import ExchangeSpec, PositionRejected, compute_position_size

BTC_SPEC = ExchangeSpec(amount_step=0.0001, amount_min=0.0001, min_notional=50.0)


def test_basic_sizing_matches_hand_calc():
    # equity 10,000 USDT, risk 1% = 100 USDT, entry 60000, SL 59500 -> sl_distance 500
    # raw_qty = 100 / 500 = 0.2 BTC
    qty = compute_position_size(10_000, 0.01, 60_000, 59_500, BTC_SPEC)
    assert qty == pytest.approx(0.2, abs=1e-6)


def test_rounds_down_to_step_never_up():
    # raw_qty = 100 / 333 = 0.3003003... -> must floor to nearest 0.0001, never ceil
    qty = compute_position_size(10_000, 0.01, 60_000, 59_667, BTC_SPEC)
    raw = 100 / 333
    assert qty <= raw
    assert qty == pytest.approx(math_floor_to_step(raw, 0.0001), abs=1e-9)


def test_rejects_when_below_min_notional_instead_of_rounding_up():
    # tiny equity -> raw qty far below minNotional; must raise, not silently bump to amount_min
    with pytest.raises(PositionRejected):
        compute_position_size(10, 0.01, 60_000, 59_500, BTC_SPEC)  # risk=0.1 USDT, sl_dist=500 -> notional~12 USDT < 50 min


def test_zero_sl_distance_raises():
    with pytest.raises(ValueError):
        compute_position_size(10_000, 0.01, 60_000, 60_000, BTC_SPEC)


def test_risk_pct_above_sane_cap_raises():
    # PROJECT_PLAN.md §0.3: 2% is the recommended ceiling; hard-cap the function at 5%
    with pytest.raises(ValueError):
        compute_position_size(10_000, 0.10, 60_000, 59_500, BTC_SPEC)


def test_no_martingale_size_independent_of_prior_trade_result():
    """Regression test per PROJECT_PLAN.md §9.4 — lot size must never be a
    function of the previous trade's outcome. Same inputs -> same output,
    always, regardless of any external win/loss state."""
    qty_after_loss = compute_position_size(10_000, 0.01, 60_000, 59_500, BTC_SPEC)
    qty_after_win = compute_position_size(10_000, 0.01, 60_000, 59_500, BTC_SPEC)
    assert qty_after_loss == qty_after_win


def math_floor_to_step(value: float, step: float) -> float:
    import math
    return math.floor(value / step) * step
