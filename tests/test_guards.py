import pytest

from src.live.guards import (
    spread_guard, stale_data_guard, heartbeat_guard, retry_with_limit, RetryLimitExceeded,
    rolling_winrate_risk_multiplier,
)


def test_spread_guard_blocks_when_spread_too_wide():
    assert spread_guard(current_spread=2.0, median_spread=0.5, max_ratio=3.0) is False  # 4x median


def test_spread_guard_allows_normal_spread():
    assert spread_guard(current_spread=1.0, median_spread=0.5, max_ratio=3.0) is True  # 2x median


def test_spread_guard_fails_closed_on_zero_median():
    assert spread_guard(current_spread=1.0, median_spread=0.0) is False


def test_stale_data_guard_blocks_old_tick():
    assert stale_data_guard(last_tick_epoch=1000.0, now_epoch=1035.0, max_age_sec=30.0) is False


def test_stale_data_guard_allows_fresh_tick():
    assert stale_data_guard(last_tick_epoch=1000.0, now_epoch=1010.0, max_age_sec=30.0) is True


def test_heartbeat_guard_blocks_when_service_looks_dead():
    assert heartbeat_guard(last_heartbeat_epoch=1000.0, now_epoch=1070.0, max_age_sec=60.0) is False


def test_retry_with_limit_succeeds_after_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("transient")
        return "ok"

    result = retry_with_limit(flaky, max_retries=2)
    assert result == "ok"
    assert calls["n"] == 2


def test_retry_with_limit_raises_after_max_retries_never_loops_forever():
    calls = {"n": 0}

    def always_fails():
        calls["n"] += 1
        raise ConnectionError("permanent")

    with pytest.raises(RetryLimitExceeded):
        retry_with_limit(always_fails, max_retries=2)
    assert calls["n"] == 3  # initial attempt + 2 retries, then stop — never unbounded


def test_winrate_guard_insufficient_history_returns_full_risk():
    # only 10 trades, below min_trades=20 -> not enough signal to act on
    recent = [0.5, -1.0, -1.0, 0.3, -1.0, -1.0, -1.0, 0.2, -1.0, -1.0]
    assert rolling_winrate_risk_multiplier(recent, min_trades=20) == 1.0


def test_winrate_guard_reduces_risk_on_2023h2_style_regime():
    # mirrors the walk-forward finding: win rate ~27% over the last 20 trades
    rng_wins = [0.5] * 5 + [-1.0] * 15  # 5/20 = 25% win rate
    assert rolling_winrate_risk_multiplier(rng_wins, window=20, winrate_threshold=0.30) == 0.5


def test_winrate_guard_full_risk_when_winrate_healthy():
    healthy = [0.5] * 9 + [-1.0] * 11  # 45% win rate, above 30% threshold
    assert rolling_winrate_risk_multiplier(healthy, window=20, winrate_threshold=0.30) == 1.0


def test_winrate_guard_only_looks_at_tail_window():
    # first 20 trades were terrible, but the most recent 20 (the tail) are healthy —
    # guard must react to CURRENT conditions, not stale history
    old_bad = [-1.0] * 20
    recent_healthy = [0.5] * 9 + [-1.0] * 11
    combined = old_bad + recent_healthy
    assert rolling_winrate_risk_multiplier(combined, window=20, winrate_threshold=0.30) == 1.0


def test_winrate_guard_custom_reduced_multiplier():
    bad = [-1.0] * 15 + [0.5] * 5  # 25% win rate
    assert rolling_winrate_risk_multiplier(bad, window=20, reduced_multiplier=0.25) == 0.25
