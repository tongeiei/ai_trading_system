"""Pre-trade guards — PROJECT_PLAN.md §9.1 L3 (Market State) / §19 fail-safe matrix.

Pure functions, no exchange calls — testable without network access.
"""
import time


def spread_guard(current_spread: float, median_spread: float, max_ratio: float = 3.0) -> bool:
    """Returns True if spread is acceptable to trade. §19: spread > 3x median -> block."""
    if median_spread <= 0:
        return False  # can't evaluate, fail closed
    return current_spread <= median_spread * max_ratio


def stale_data_guard(last_tick_epoch: float, now_epoch: float | None = None, max_age_sec: float = 30.0) -> bool:
    """Returns True if price data is fresh enough to trade. §19: tick > 30s old -> block."""
    now_epoch = now_epoch if now_epoch is not None else time.time()
    return (now_epoch - last_tick_epoch) <= max_age_sec


def heartbeat_guard(last_heartbeat_epoch: float, now_epoch: float | None = None, max_age_sec: float = 60.0) -> bool:
    """Returns True if the signal-generating process is alive. §19: heartbeat > 60s old -> block new signals."""
    now_epoch = now_epoch if now_epoch is not None else time.time()
    return (now_epoch - last_heartbeat_epoch) <= max_age_sec


def rolling_winrate_risk_multiplier(
    recent_r_multiples: list[float],
    window: int = 20,
    winrate_threshold: float = 0.30,
    min_trades: int = 20,
    reduced_multiplier: float = 0.5,
) -> float:
    """Early-warning risk cut, added after docs/FINDINGS.md's 2023-H2 walk-forward
    result: a whipsaw regime showed win rate ~27% and both LONG/SHORT losing
    together, well before daily-loss or drawdown thresholds would have fired.

    Checks the win rate over the last `window` CLOSED trades (net_r_multiple,
    ordered oldest->newest — only the tail is used). If it's below
    `winrate_threshold`, returns `reduced_multiplier` (halve risk by default)
    instead of waiting for DD/daily-loss to catch up.

    Returns 1.0 (no reduction) if fewer than `min_trades` are available —
    a rolling window this short is too noisy to act on with fewer samples
    than that (see §14.4 sample-size discipline).
    """
    if len(recent_r_multiples) < min_trades:
        return 1.0

    tail = recent_r_multiples[-window:]
    win_rate = sum(1 for r in tail if r > 0) / len(tail)
    return reduced_multiplier if win_rate < winrate_threshold else 1.0


class RetryLimitExceeded(Exception):
    pass


def retry_with_limit(fn, max_retries: int = 2, on_retry=None):
    """§9.4: retry <= 2 times, then give up and raise — NEVER retry unlimited.
    An unbounded retry loop on order placement is exactly the kind of bug that
    turns a transient error into a duplicate/runaway order.
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                if on_retry:
                    on_retry(attempt, e)
                continue
    raise RetryLimitExceeded(f"failed after {max_retries} retries: {last_exc}") from last_exc
