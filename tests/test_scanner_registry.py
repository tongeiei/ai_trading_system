"""Tests for src/scanner/registry.py + src/scanner/__init__.py::scan()
(docs/XAU_ARCHITECTURE_AUDIT.md P5)."""
import numpy as np
import pandas as pd
from sqlalchemy import select

from src.data.db import init_db, setups
from src.scanner import scan
from src.scanner.registry import (
    REGISTRY, SETUP_CATEGORIES, SETUP_STATUSES, get_setups, sync_registry_to_db,
)

SCANNABLE_IDS = {"gold_r14_fake_zone", "gold_r15_choch", "gold_r17_fvg"}


def test_every_entry_has_valid_status_and_category():
    for s in REGISTRY:
        assert s.status in SETUP_STATUSES, f"{s.setup_id} has invalid status {s.status}"
        assert s.category in SETUP_CATEGORIES, f"{s.setup_id} has invalid category {s.category}"


def test_exactly_three_entries_are_scannable():
    scannable = [s for s in REGISTRY if s.scannable]
    assert {s.setup_id for s in scannable} == SCANNABLE_IDS
    for s in scannable:
        assert s.detect_fn is not None


def test_get_setups_rejected_count_matches_registry():
    expected = len([s for s in REGISTRY if s.status == "REJECTED"])
    assert len(get_setups(status="REJECTED")) == expected
    assert expected == 10  # 8 gold R-strategies + breakout + mean_reversion


def test_get_setups_market_filter():
    crypto = get_setups(market="crypto")
    assert {s.setup_id for s in crypto} == {
        "eth_v0_ema_pullback", "xrp_v0_ema_pullback",
        "crypto_donchian_breakout", "crypto_mean_reversion",
    }


def _synthetic_m15(n=200, seed=1):
    rng = np.random.default_rng(seed)
    times = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    price = 2000 + np.cumsum(rng.normal(0, 1, size=n))
    return pd.DataFrame({
        "time_utc": times,
        "open": price, "close": price,
        "high": price + rng.uniform(0.5, 2, size=n),
        "low": price - rng.uniform(0.5, 2, size=n),
        "volume": rng.uniform(10, 100, size=n),
    })


def test_scan_default_statuses_returns_empty():
    out = scan(_synthetic_m15())
    assert out == {}


def test_scan_rejected_status_runs_three_wired_adapters():
    out = scan(_synthetic_m15(), statuses=("REJECTED",))
    assert set(out.keys()) == SCANNABLE_IDS
    for df in out.values():
        assert "time_utc" in df.columns
        assert "signal" in df.columns
        assert len(df) == 200


def test_sync_registry_to_db_round_trip(tmp_path):
    engine = init_db(str(tmp_path / "test.db"))
    n = sync_registry_to_db(engine)
    assert n == len(REGISTRY)

    with engine.connect() as conn:
        rows = conn.execute(select(setups)).fetchall()
    assert len(rows) == len(REGISTRY)
    live_rows = [r for r in rows if r.setup_id == "eth_v0_ema_pullback"]
    assert len(live_rows) == 1
    assert live_rows[0].status == "LIVE"


def test_sync_registry_to_db_is_idempotent(tmp_path):
    engine = init_db(str(tmp_path / "test.db"))
    sync_registry_to_db(engine)
    n2 = sync_registry_to_db(engine)
    assert n2 == len(REGISTRY)
    with engine.connect() as conn:
        rows = conn.execute(select(setups)).fetchall()
    assert len(rows) == len(REGISTRY)
