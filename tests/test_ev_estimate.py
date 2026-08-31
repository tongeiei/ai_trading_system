import pytest

from src.live.ev_estimate import estimate_ev, EV_THRESHOLD_R, SYMBOL_STATS


def test_ev_positive_when_sl_distance_wide_relative_to_price():
    # wide SL (15% of price) dilutes commission/slippage cost in R-terms to
    # ~0 -> EV approaches the symbol's gross edge. XRP's gross edge (~0.175R)
    # clears the 0.15R gate; ETH's (~0.074R, post cost-model-fix) does not
    # — see test below. Uses XRP here specifically because it's the symbol
    # for which "wide SL clears the gate" is actually true right now.
    est = estimate_ev("XRP/USDT:USDT", entry_price=60_000, sl_distance=9000)
    assert est.ev_r > EV_THRESHOLD_R
    assert est.passes_gate is True


def test_eth_gross_edge_no_longer_clears_gate_even_at_wide_sl():
    # Regression-documenting test: after the 2026-08-28 cost-model-driven
    # recalibration (docs/research/BTC_EDGE_SEARCH.md Round 6), ETH's own
    # gross edge (~0.074R full-period) sits BELOW the 0.15R gate threshold
    # before any cost is even subtracted, so no SL width can rescue it.
    # This is intentional (Trading Lead decision: the gate rejecting ETH is
    # correct behavior, not a bug) — if this test ever starts failing
    # because someone widened the gate/edge back to "pass", that's a signal
    # to check whether it was a legitimate re-validation or a rescue-tune.
    est = estimate_ev("ETH/USDT:USDT", entry_price=60_000, sl_distance=9000)
    assert est.passes_gate is False


def test_ev_negative_when_sl_distance_narrow_relative_to_price():
    # narrow SL (0.1% of price) makes cost dominate in R-terms, same
    # commission-drag mechanism found in the original cost-model backtest
    est = estimate_ev("ETH/USDT:USDT", entry_price=60_000, sl_distance=60)
    assert est.passes_gate is False


def test_cost_in_r_terms_shrinks_as_sl_widens():
    # commission/slippage are ~fixed in PRICE terms (taker_fee * price), so as
    # a fraction of a WIDER stop distance (i.e. in R-multiples) they shrink —
    # this is the exact mechanism behind the "widen SL to dilute commission
    # drag" finding from earlier in the project
    narrow = estimate_ev("ETH/USDT:USDT", entry_price=60_000, sl_distance=60)
    wide = estimate_ev("ETH/USDT:USDT", entry_price=60_000, sl_distance=1200)
    assert wide.cost_r < narrow.cost_r


def test_trading_cost_pct_is_roughly_price_invariant_to_sl_width():
    # cost_r ~ 1/sl_distance and expected_move_pct conversion ~ sl_distance,
    # so trading_cost_pct (cost expressed as % of PRICE) stays ~constant
    # regardless of stop width — a real property of fixed-% commission, not a bug
    narrow = estimate_ev("ETH/USDT:USDT", entry_price=60_000, sl_distance=60)
    wide = estimate_ev("ETH/USDT:USDT", entry_price=60_000, sl_distance=1200)
    assert narrow.trading_cost_pct == pytest.approx(wide.trading_cost_pct, rel=1e-9)


def test_win_rate_and_avg_win_loss_are_historical_constants_not_dynamic_per_symbol():
    # for a FIXED symbol, stats don't move with price/sl_distance
    est1 = estimate_ev("ETH/USDT:USDT", entry_price=60_000, sl_distance=500)
    est2 = estimate_ev("ETH/USDT:USDT", entry_price=2_500, sl_distance=50)
    assert est1.win_rate == est2.win_rate


def test_symbols_use_their_own_stats_not_borrowed_from_another_symbol():
    # regression test for the bug where XRP silently used ETH's CAL-fold
    # stats (docs/research/BTC_EDGE_SEARCH.md Round 6 audit finding) —
    # ETH and XRP's V0 setups fire in different regimes and have genuinely
    # different historical win_rate/avg_win/avg_loss, so they must not match
    eth = estimate_ev("ETH/USDT:USDT", entry_price=2_500, sl_distance=50)
    xrp = estimate_ev("XRP/USDT:USDT", entry_price=2_500, sl_distance=50)
    assert eth.win_rate != xrp.win_rate
    assert eth.avg_win_r != xrp.avg_win_r
    assert eth.avg_loss_r != xrp.avg_loss_r
    assert eth.win_rate == SYMBOL_STATS["ETH/USDT:USDT"]["win_rate"]
    assert xrp.win_rate == SYMBOL_STATS["XRP/USDT:USDT"]["win_rate"]


def test_missing_symbol_fails_loudly_not_silently():
    with pytest.raises(KeyError):
        estimate_ev("DOGE/USDT:USDT", entry_price=1.0, sl_distance=0.01)
