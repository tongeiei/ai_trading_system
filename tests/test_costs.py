import pandas as pd
import pytest

from src.backtest.costs import commission_cost_r, funding_cost_r, slippage_cost_r


def test_commission_cost_matches_hand_calc():
    # entry_price=60000, taker_fee=0.0005, sl_distance=500
    # round-trip commission = 2 * 0.0005 * 60000 = 60 USD -> 60/500 = 0.12R
    r = commission_cost_r(sl_distance=500, entry_price=60_000, taker_fee=0.0005)
    assert r == pytest.approx(0.12, abs=1e-9)


def test_slippage_cost_matches_hand_calc():
    # 2 * 0.5 / 500 = 0.002R
    r = slippage_cost_r(sl_distance=500, slippage_price_units=0.5)
    assert r == pytest.approx(0.002, abs=1e-9)


def test_funding_cost_long_pays_when_rate_positive():
    entry_time = pd.Timestamp("2024-01-01 00:00", tz="UTC")
    exit_time = pd.Timestamp("2024-01-01 09:00", tz="UTC")  # spans one funding event at 08:00
    funding_rates = pd.DataFrame({
        "time_utc": [pd.Timestamp("2024-01-01 08:00", tz="UTC")],
        "funding_rate": [0.0001],
    })
    r = funding_cost_r(entry_time, exit_time, entry_price=60_000, action="LONG",
                        sl_distance=500, funding_rates=funding_rates)
    # cost = 0.0001 * 60000 = 6 USD -> 6/500 = 0.012R, positive (a cost) for LONG
    assert r == pytest.approx(0.012, abs=1e-9)


def test_funding_cost_short_receives_when_rate_positive():
    entry_time = pd.Timestamp("2024-01-01 00:00", tz="UTC")
    exit_time = pd.Timestamp("2024-01-01 09:00", tz="UTC")
    funding_rates = pd.DataFrame({
        "time_utc": [pd.Timestamp("2024-01-01 08:00", tz="UTC")],
        "funding_rate": [0.0001],
    })
    r = funding_cost_r(entry_time, exit_time, entry_price=60_000, action="SHORT",
                        sl_distance=500, funding_rates=funding_rates)
    # SHORT receives when funding is positive -> negative cost (a credit)
    assert r == pytest.approx(-0.012, abs=1e-9)


def test_funding_cost_zero_when_no_events_in_window():
    entry_time = pd.Timestamp("2024-01-01 00:00", tz="UTC")
    exit_time = pd.Timestamp("2024-01-01 01:00", tz="UTC")  # no funding event crossed
    funding_rates = pd.DataFrame({
        "time_utc": [pd.Timestamp("2024-01-01 08:00", tz="UTC")],
        "funding_rate": [0.0001],
    })
    r = funding_cost_r(entry_time, exit_time, entry_price=60_000, action="LONG",
                        sl_distance=500, funding_rates=funding_rates)
    assert r == 0.0


def test_funding_cost_zero_when_exit_time_missing():
    entry_time = pd.Timestamp("2024-01-01 00:00", tz="UTC")
    funding_rates = pd.DataFrame({"time_utc": [], "funding_rate": []})
    r = funding_cost_r(entry_time, pd.NaT, entry_price=60_000, action="LONG",
                        sl_distance=500, funding_rates=funding_rates)
    assert r == 0.0
