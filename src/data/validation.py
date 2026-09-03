"""OHLCV data-quality validation — gap/outlier/reconciliation/session checks.

Part of P2 (docs/XAU_ARCHITECTURE_AUDIT.md §10) — this is the first data-quality
validation layer in the repo; previously only dedupe+sort+print-only gap reports
existed in the fetch scripts (see scripts/fetch_xau_dukascopy.py).

Functions report issues rather than raising: a future live monitor loop must not
die on a single bad bar. Callers decide what to do with ValidationReport.ok.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

TIMEFRAME_STEPS = {
    "1m": pd.Timedelta(minutes=1),
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
}


@dataclasses.dataclass
class ValidationIssue:
    kind: str       # "gap" | "outlier" | "reconciliation" | "session"
    severity: str   # "warn" | "error"
    time_utc: pd.Timestamp | None
    detail: str


@dataclasses.dataclass
class ValidationReport:
    timeframe: str
    n_bars: int
    issues: list[ValidationIssue]

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def summary(self) -> str:
        n_error = sum(1 for i in self.issues if i.severity == "error")
        n_warn = sum(1 for i in self.issues if i.severity == "warn")
        status = "OK" if self.ok else "FAIL"
        return (
            f"[{self.timeframe}] {status} — {self.n_bars} bars, "
            f"{n_error} error(s), {n_warn} warning(s)"
        )


def _is_expected_quiet_gap(start: pd.Timestamp, end: pd.Timestamp) -> bool:
    """True if [start, end) plausibly overlaps a known low/no-liquidity window:
    the recurring DAILY thin-liquidity/rollover period seen in real Dukascopy
    data (empirically ~20:45-22:00 UTC every trading day, not just weekends —
    confirmed by running scripts/fetch_xau_dukascopy.py against real data,
    which otherwise floods the report with a false "error" every single
    trading day across 20 years of history), plus the full Fri-close/Sun-open
    weekly forex closure. Loose by design (any hour >=20:00 UTC on any day,
    all Saturday, Sunday <23:00 UTC) since exact broker quiet-period/DST
    boundaries vary by venue — false negatives here (missing a genuine
    daytime outage that happens to touch this window) are preferable to
    burying real gaps under thousands of expected ones."""
    cur = start
    while cur < end:
        if cur.hour >= 20 or cur.dayofweek == 5 or (cur.dayofweek == 6 and cur.hour < 23):
            return True
        cur += pd.Timedelta(hours=1)
    return False


def detect_gaps(
    df: pd.DataFrame, timeframe: str, *, gap_multiple: float = 1.5
) -> list[ValidationIssue]:
    """Flags gaps > gap_multiple * expected step. A gap overlapping a known
    quiet window (daily thin-liquidity period or the weekly weekend closure,
    see _is_expected_quiet_gap) is classified 'warn' (expected); anything
    else beyond the threshold is 'error'."""
    step = TIMEFRAME_STEPS[timeframe]
    issues: list[ValidationIssue] = []
    if len(df) < 2:
        return issues
    times = df["time_utc"].reset_index(drop=True)
    threshold = step * gap_multiple

    # Vectorized threshold check over the whole series (fast even at millions
    # of rows); the Python loop below only runs over the much smaller set of
    # positions that actually exceed the threshold (a few thousand daily/
    # weekend quiet windows across 20y of history, not every row).
    deltas_ns = times.diff().to_numpy()
    mask = deltas_ns > np.timedelta64(threshold)
    flagged_positions = np.nonzero(mask)[0]

    for pos in flagged_positions:
        gap = pd.Timedelta(deltas_ns[pos])
        prev_t = times.iloc[pos - 1]
        cur_t = times.iloc[pos]
        if _is_expected_quiet_gap(prev_t, cur_t):
            issues.append(
                ValidationIssue(
                    "gap", "warn", cur_t,
                    f"gap of {gap} after {prev_t} — expected quiet window (daily/weekend)",
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    "gap", "error", cur_t,
                    f"gap of {gap} after {prev_t} — exceeds {threshold}",
                )
            )
    return issues


def detect_outliers(
    df: pd.DataFrame, *, max_bar_move_pct: float = 5.0, zscore_threshold: float = 8.0
) -> list[ValidationIssue]:
    """Bad-tick catcher: single-bar close-to-close % move, or bar range
    z-scoring far outside its rolling window. Thresholds are intentionally
    loose — gold can move fast around news, which this system does not filter
    (docs/XAU_ARCHITECTURE_AUDIT.md §15 item 10) — this is for bad ticks, not
    volatility filtering."""
    issues: list[ValidationIssue] = []
    if len(df) < 2:
        return issues

    close = df["close"]
    pct_move = (close / close.shift(1) - 1.0).abs() * 100.0
    bad_moves = pct_move[pct_move > max_bar_move_pct]
    for idx in bad_moves.index:
        issues.append(
            ValidationIssue(
                "outlier", "error", df["time_utc"].loc[idx],
                f"close moved {pct_move.loc[idx]:.2f}% vs prior bar (> {max_bar_move_pct}%)",
            )
        )

    bar_range = df["high"] - df["low"]
    window = min(50, max(5, len(df) // 10 or 5))
    rolling_std = bar_range.rolling(window, min_periods=5).std()
    rolling_mean = bar_range.rolling(window, min_periods=5).mean()
    zscore = (bar_range - rolling_mean) / rolling_std.replace(0, np.nan)
    bad_range = zscore[zscore.abs() > zscore_threshold]
    for idx in bad_range.index:
        if df["time_utc"].loc[idx] in {i.time_utc for i in issues}:
            continue
        issues.append(
            ValidationIssue(
                "outlier", "error", df["time_utc"].loc[idx],
                f"bar range z-score {zscore.loc[idx]:.1f} (> {zscore_threshold})",
            )
        )
    return issues


def reconcile_sources(
    primary: pd.DataFrame,
    secondary: pd.DataFrame,
    *,
    timeframe: str,
    tolerance_bps: float = 5.0,
) -> list[ValidationIssue]:
    """Bar-for-bar close comparison between two same-timeframe frames on
    overlapping timestamps (e.g. natively-fetched M5 vs M1-resampled-to-5m).
    Source-agnostic — later usable for Dukascopy vs MT5 without changes."""
    issues: list[ValidationIssue] = []
    merged = primary[["time_utc", "close"]].merge(
        secondary[["time_utc", "close"]], on="time_utc", suffixes=("_primary", "_secondary")
    )
    if merged.empty:
        issues.append(
            ValidationIssue(
                "reconciliation", "warn", None,
                "no overlapping timestamps between primary and secondary sources",
            )
        )
        return issues

    diff_bps = (
        (merged["close_primary"] - merged["close_secondary"]) / merged["close_secondary"]
    ).abs() * 10000.0
    bad = merged[diff_bps > tolerance_bps]
    for _, row in bad.iterrows():
        issues.append(
            ValidationIssue(
                "reconciliation", "error", row["time_utc"],
                f"close diverges {row['close_primary']} vs {row['close_secondary']} "
                f"(> {tolerance_bps} bps)",
            )
        )
    return issues


def check_session_coverage(
    df: pd.DataFrame, *, window_utc: tuple[int, int] = (1, 15)
) -> list[ValidationIssue]:
    """Coverage report against the locked trading window (01:00-15:00 UTC,
    docs/XAU_ARCHITECTURE_AUDIT.md §15 item 1) — reports bar-presence %, not a
    filter. No holiday calendar exists yet, so a full-window weekday absence is
    'warn' (candidate holiday), not 'error' — building a real holiday calendar
    is deferred to a later phase."""
    issues: list[ValidationIssue] = []
    if df.empty:
        return issues

    start_h, end_h = window_utc
    weekdays = df[df["time_utc"].dt.dayofweek < 5]
    if weekdays.empty:
        return issues

    # Vectorized: one boolean column + groupby, instead of re-scanning the
    # whole frame per calendar day (which is O(n_bars * n_days) and grinds
    # to a halt on 20y of M15/M1 history — a few hundred thousand rows times
    # a few thousand days is billions of comparisons).
    in_window_mask = (weekdays["time_utc"].dt.hour >= start_h) & (
        weekdays["time_utc"].dt.hour < end_h
    )
    coverage = in_window_mask.groupby(weekdays["time_utc"].dt.date).any()
    missing_dates = coverage[~coverage].index

    for d in missing_dates:
        issues.append(
            ValidationIssue(
                "session", "warn", pd.Timestamp(d, tz="UTC"),
                f"no bars in {start_h:02d}:00-{end_h:02d}:00 UTC window on weekday {d} "
                "— candidate holiday (no calendar to confirm against)",
            )
        )
    return issues


def validate_timeframe(
    df: pd.DataFrame, timeframe: str, *, secondary: pd.DataFrame | None = None
) -> ValidationReport:
    """Runs all checks and aggregates into one report."""
    issues: list[ValidationIssue] = []
    issues += detect_gaps(df, timeframe)
    issues += detect_outliers(df)
    issues += check_session_coverage(df)
    if secondary is not None:
        issues += reconcile_sources(df, secondary, timeframe=timeframe)
    return ValidationReport(timeframe=timeframe, n_bars=len(df), issues=issues)
