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
