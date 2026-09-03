import pandas as pd

from src.data.validation import (
    check_session_coverage,
    detect_gaps,
    detect_outliers,
    reconcile_sources,
    validate_timeframe,
)


def _clean_m15(n_bars=200, start_date="2026-01-05"):
    """Continuous (all-day) M15 series on weekdays only, starting on a Monday,
    with mild realistic price noise. Mirrors real forex data: bars run the
    full 24h each trading day (not just the 01:00-15:00 policy window used
    elsewhere) — the only expected large gap is the weekly weekend closure."""
    day = pd.Timestamp(start_date, tz="UTC")
    times = []
    while len(times) < n_bars:
        if day.dayofweek < 5:
            day_times = pd.date_range(day, periods=96, freq="15min", tz="UTC")
            times.extend(list(day_times))
        day += pd.Timedelta(days=1)
    times = pd.DatetimeIndex(times[:n_bars])
    n = len(times)
    price = 2000.0 + pd.Series(range(n)).mul(0.05).to_numpy()
    df = pd.DataFrame(
        {
            "time_utc": times,
            "open": price,
            "high": price + 0.3,
            "low": price - 0.3,
            "close": price + 0.05,
            "volume": 100.0,
        }
    ).reset_index(drop=True)
    return df


def test_detect_gaps_flags_intraweek_gap():
    df = _clean_m15(n_bars=150)
    # remove 3 hours of Tuesday bars mid-series to create a real gap
    tuesday = df[df["time_utc"].dt.dayofweek == 1]
    assert not tuesday.empty
    drop_start = tuesday["time_utc"].iloc[2]
    drop_end = drop_start + pd.Timedelta(hours=3)
    mask = ~((df["time_utc"] >= drop_start) & (df["time_utc"] < drop_end))
    df = df[mask].reset_index(drop=True)

    issues = detect_gaps(df, "15m")
    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) == 1
    assert errors[0].kind == "gap"


def test_detect_gaps_does_not_flag_weekend_close():
    # Friday 14:45 UTC -> Monday 01:00 UTC (the weekly forex closure)
    times = list(pd.date_range("2026-01-02 01:00:00", periods=5, freq="15min", tz="UTC"))
    times += list(pd.date_range("2026-01-05 01:00:00", periods=5, freq="15min", tz="UTC"))
    n = len(times)
    price = [2000.0 + i * 0.1 for i in range(n)]
    df = pd.DataFrame(
        {
            "time_utc": times,
            "open": price,
            "high": [p + 0.3 for p in price],
            "low": [p - 0.3 for p in price],
            "close": [p + 0.05 for p in price],
            "volume": 100.0,
        }
    )

    issues = detect_gaps(df, "15m")
    errors = [i for i in issues if i.severity == "error"]
    assert errors == []
    warns = [i for i in issues if i.severity == "warn"]
    assert len(warns) == 1


def test_detect_outliers_flags_bad_tick():
    df = _clean_m15(n_bars=60)
    bad_idx = 30
    df.loc[bad_idx, "close"] = df.loc[bad_idx - 1, "close"] * 1.2  # +20% bad tick
    df.loc[bad_idx, "high"] = df.loc[bad_idx, "close"] + 0.3
    df.loc[bad_idx, "low"] = df.loc[bad_idx, "close"] - 0.3

    issues = detect_outliers(df)
    assert any(i.kind == "outlier" and i.severity == "error" for i in issues)


def test_detect_outliers_allows_normal_volatility():
    df = _clean_m15(n_bars=60)
    issues = detect_outliers(df)
    assert issues == []


def test_reconcile_sources_agree():
    df = _clean_m15(n_bars=30)
    issues = reconcile_sources(df, df.copy(), timeframe="15m")
    assert issues == []


def test_reconcile_sources_flags_divergence():
    primary = _clean_m15(n_bars=30)
    secondary = primary.copy()
    secondary["close"] = secondary["close"] * 1.01  # 100 bps off, well above tolerance

    issues = reconcile_sources(primary, secondary, timeframe="15m", tolerance_bps=5.0)
    assert len(issues) == len(primary)
    assert all(i.kind == "reconciliation" and i.severity == "error" for i in issues)


def test_check_session_coverage_reports_window():
    df = _clean_m15(n_bars=200)
    issues = check_session_coverage(df)
    assert all(i.severity == "warn" for i in issues)
    # a fully-covered synthetic week should not have every weekday flagged
    n_weekdays = len(df["time_utc"].dt.date.unique())
    assert len(issues) < n_weekdays


def test_validate_timeframe_ok_report_has_no_errors():
    df = _clean_m15(n_bars=100)
    report = validate_timeframe(df, "15m")
    assert report.ok is True
    assert report.n_bars == 100


def test_validate_timeframe_bad_report_ok_false():
    df = _clean_m15(n_bars=150)
    bad_idx = 30
    df.loc[bad_idx, "close"] = df.loc[bad_idx - 1, "close"] * 1.2
    tuesday = df[df["time_utc"].dt.dayofweek == 1]
    drop_start = tuesday["time_utc"].iloc[2]
    drop_end = drop_start + pd.Timedelta(hours=3)
    mask = ~((df["time_utc"] >= drop_start) & (df["time_utc"] < drop_end))
    df = df[mask].reset_index(drop=True)

    report = validate_timeframe(df, "15m")
    assert report.ok is False
    kinds = {i.kind for i in report.issues if i.severity == "error"}
    assert "gap" in kinds
    assert "outlier" in kinds
