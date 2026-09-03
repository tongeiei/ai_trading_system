"""Tests for src/ai/scorecard.py (docs/XAU_ARCHITECTURE_AUDIT.md P6 remainder --
the deterministic 6-channel scorecard, NOT yet validated by the bucket test in
scripts/bucket_test_scorecard.py)."""
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from src.ai.scorecard import (
    Scorecard, compute_scorecard, compute_scorecard_batch, gate,
    _momentum_score, _risk_score, _session_score, _structure_score, _trend_score,
    _volatility_score,
)
from src.data.db import init_db, scorecard_log
from src.live.logging_store import log_scorecard_batch


def test_trend_score_higher_when_aligned_and_strong():
    aligned_strong = _trend_score(f03_h1_trend_atr=1.5, f04_adx14_h1=35, direction="LONG")
    aligned_weak_adx = _trend_score(f03_h1_trend_atr=1.5, f04_adx14_h1=5, direction="LONG")
    opposed = _trend_score(f03_h1_trend_atr=1.5, f04_adx14_h1=35, direction="SHORT")
    assert aligned_strong > aligned_weak_adx > 50
    assert opposed < 50
    assert aligned_strong > opposed


def test_trend_score_neutral_when_flat():
    assert _trend_score(f03_h1_trend_atr=0.0, f04_adx14_h1=30, direction="LONG") == pytest.approx(50, abs=1)


def test_structure_score_higher_when_aligned_with_room():
    aligned = _structure_score(
        f19_dist_swing_high_atr=2.0, f20_dist_swing_low_atr=0.2,
        f21_trend_state=1, f22_bos_fired=1, direction="LONG",
    )
    opposed = _structure_score(
        f19_dist_swing_high_atr=0.1, f20_dist_swing_low_atr=0.2,
        f21_trend_state=-1, f22_bos_fired=-1, direction="LONG",
    )
    assert aligned > 50 > opposed


def test_momentum_score_direction_aware():
    long_positive = _momentum_score(f05_logret_4=0.01, f06_logret_12=0.02, direction="LONG")
    short_positive = _momentum_score(f05_logret_4=0.01, f06_logret_12=0.02, direction="SHORT")
    assert long_positive > 50 > short_positive


def test_volatility_score_linear_in_percentile():
    low = _volatility_score(f08_atr_percentile=0.1)
    high = _volatility_score(f08_atr_percentile=0.9)
    assert low < high
    assert _volatility_score(f08_atr_percentile=np.nan) == 50.0  # neutral fallback


def test_session_score_ranking():
    assert _session_score("OVERLAP") > _session_score("LONDON") > _session_score("NY")
    assert _session_score("NY") > _session_score("ASIA") > _session_score("OFF")
    assert _session_score("UNKNOWN_SESSION") == 50.0


def test_risk_score_peaks_near_ideal_sl_atr():
    ideal = _risk_score(sl_distance=1.5 * 10, atr_at_entry=10)   # 1.5x ATR
    tight = _risk_score(sl_distance=0.2 * 10, atr_at_entry=10)   # 0.2x ATR
    wide = _risk_score(sl_distance=5.0 * 10, atr_at_entry=10)    # 5x ATR
    assert ideal > tight
    assert ideal > wide
    assert _risk_score(sl_distance=1.0, atr_at_entry=0) == 50.0  # guarded, no div-by-zero


def _neutral_row():
    return pd.Series({
        "f03_h1_trend_atr": 0.0, "f04_adx14_h1": 20.0,
        "f19_dist_swing_high_atr": 1.0, "f20_dist_swing_low_atr": 1.0,
        "f21_trend_state": 0, "f22_bos_fired": 0,
        "f05_logret_4": 0.0, "f06_logret_12": 0.0,
        "f08_atr_percentile": 0.5, "session": "LONDON",
    })


def test_final_score_is_unweighted_mean_of_six_channels():
    sc = compute_scorecard(_neutral_row(), direction="LONG", sl_distance=15.0, atr_at_entry=10.0)
    channels = [sc.trend, sc.structure, sc.momentum, sc.volatility, sc.session, sc.risk]
    assert sc.final_score == pytest.approx(np.mean(channels))


def test_weakest_link_block_independent_of_average():
    row = _neutral_row()
    row["f04_adx14_h1"] = 0  # drags trend toward 50, not below 50 alone
    sc_ok = compute_scorecard(row, direction="LONG", sl_distance=15.0, atr_at_entry=10.0)
    assert not sc_ok.weakest_link_block

    # force one channel below 50 (session=OFF) while others stay high, so the
    # average alone would clear 60 but weakest-link must still block.
    row2 = _neutral_row()
    row2["session"] = "OFF"
    row2["f03_h1_trend_atr"] = 3.0
    row2["f04_adx14_h1"] = 40
    row2["f21_trend_state"] = 1
    row2["f22_bos_fired"] = 1
    row2["f19_dist_swing_high_atr"] = 3.0
    row2["f05_logret_4"] = 0.01
    row2["f06_logret_12"] = 0.01
    row2["f08_atr_percentile"] = 0.9
    sc_blocked = compute_scorecard(row2, direction="LONG", sl_distance=15.0, atr_at_entry=10.0)
    assert sc_blocked.weakest_link_block
    assert sc_blocked.session < 50


def test_gate_bands():
    lo = Scorecard(50, 50, 50, 50, 50, 50, final_score=50, weakest_link_block=False)
    mid = Scorecard(70, 70, 70, 70, 70, 70, final_score=70, weakest_link_block=False)
    hi = Scorecard(90, 90, 90, 90, 90, 90, final_score=90, weakest_link_block=False)
    blocked_but_high = Scorecard(90, 90, 90, 90, 90, 40, final_score=76.67, weakest_link_block=True)

    assert gate(lo).decision == "NO_TRADE" and gate(lo).risk_pct == 0.0
    assert gate(mid).decision == "SMALL_RISK" and gate(mid).risk_pct == 0.25
    assert gate(hi).decision == "NORMAL_RISK" and gate(hi).risk_pct == 0.5
    assert gate(blocked_but_high).decision == "NO_TRADE"


def _synthetic_m15h1(n=300, seed=7):
    rng = np.random.default_rng(seed)
    m15_times = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    price = 2000 + np.cumsum(rng.normal(0, 1, size=n))
    m15 = pd.DataFrame({
        "time_utc": m15_times, "open": price, "close": price,
        "high": price + rng.uniform(0.5, 2, size=n), "low": price - rng.uniform(0.5, 2, size=n),
        "volume": rng.uniform(10, 100, size=n),
    })
    h1_times = pd.date_range("2024-01-01", periods=n // 4 + 5, freq="1h", tz="UTC")
    h1_price = 2000 + np.cumsum(rng.normal(0, 2, size=len(h1_times)))
    h1 = pd.DataFrame({
        "time_utc": h1_times, "open": h1_price, "close": h1_price,
        "high": h1_price + 2, "low": h1_price - 2, "volume": rng.uniform(50, 500, size=len(h1_times)),
    })
    return m15, h1


def _synthetic_trades(m15, n=20, seed=3):
    rng = np.random.default_rng(seed)
    idx = rng.choice(range(250, len(m15)), size=n, replace=False)
    rows = []
    for i in idx:
        action = "LONG" if rng.random() > 0.5 else "SHORT"
        rows.append({
            "time_utc": m15.iloc[i]["time_utc"], "close": m15.iloc[i]["close"],
            "action": action, "sl_price": m15.iloc[i]["close"] - 10, "tp_price": m15.iloc[i]["close"] + 15,
            "sl_distance": 10.0,
        })
    return pd.DataFrame(rows).sort_values("time_utc").reset_index(drop=True)


def test_compute_scorecard_batch_shape_and_columns():
    m15, h1 = _synthetic_m15h1()
    trades = _synthetic_trades(m15)
    out = compute_scorecard_batch(m15, h1, trades)
    assert len(out) == len(trades)
    for col in ["trend", "structure", "momentum", "volatility", "session", "risk",
                "final_score", "weakest_link_block"]:
        assert col in out.columns
    assert out["final_score"].between(0, 100).all()


def test_compute_scorecard_batch_no_lookahead():
    m15, h1 = _synthetic_m15h1()
    trades = _synthetic_trades(m15)
    trades = trades[trades["time_utc"] < m15["time_utc"].iloc[-5]]  # keep entries away from the truncated tail

    full = compute_scorecard_batch(m15, h1, trades)
    truncated = compute_scorecard_batch(m15.iloc[:-3].copy(), h1, trades)

    pd.testing.assert_frame_equal(
        full[["trend", "structure", "momentum", "volatility", "session", "risk", "final_score"]].reset_index(drop=True),
        truncated[["trend", "structure", "momentum", "volatility", "session", "risk", "final_score"]].reset_index(drop=True),
    )


def test_log_scorecard_batch_round_trip(tmp_path):
    m15, h1 = _synthetic_m15h1()
    trades = _synthetic_trades(m15)
    trades["net_r_multiple"] = np.linspace(-0.5, 0.5, len(trades))
    scored = compute_scorecard_batch(m15, h1, trades)
    scored["strategy"] = "test_strategy"
    scored["decision"] = [gate(Scorecard(
        r.trend, r.structure, r.momentum, r.volatility, r.session, r.risk,
        r.final_score, bool(r.weakest_link_block),
    )).decision for r in scored.itertuples()]
    scored["risk_pct"] = [gate(Scorecard(
        r.trend, r.structure, r.momentum, r.volatility, r.session, r.risk,
        r.final_score, bool(r.weakest_link_block),
    )).risk_pct for r in scored.itertuples()]

    engine = init_db(str(tmp_path / "test.db"))
    n = log_scorecard_batch(engine, "XAUUSD", "M15", scored)
    assert n == len(scored)

    with engine.connect() as conn:
        rows = conn.execute(select(scorecard_log)).fetchall()
    assert len(rows) == len(scored)
    assert rows[0].strategy == "test_strategy"
    assert rows[0].symbol == "XAUUSD"
    assert rows[0].veto is None
    assert rows[0].actual_net_r_multiple is not None
    assert rows[0].decision in ("NO_TRADE", "SMALL_RISK", "NORMAL_RISK")
