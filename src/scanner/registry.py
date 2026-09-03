"""Setup registry + status lifecycle, per docs/XAU_ARCHITECTURE_AUDIT.md P5
(TASK_NEW_WORLD.md §10: RESEARCH -> CANDIDATE -> VALIDATED -> PAPER -> LIVE / REJECTED).

Every setup implementation in src/strategy/ is registered here with its status
sourced from existing docs (docs/HANDOFF.md, docs/FINDINGS.md,
docs/research/GOLD_HANDOFF.md, CLAUDE.md) -- this module does not re-run or
re-judge any backtest, it only catalogs what's already been decided.

Only 3 entries are "scannable" (have a wired detect_fn) as of P5 -- see
docs/XAU_ARCHITECTURE_AUDIT.md §17 for why the rest (including the LIVE
v0_rules.py ETH/XRP configs) are metadata-only. Nothing here imports or calls
src/live/ or src/strategy/v0_rules.py.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd

from src.data.db import setups as setups_table

SETUP_STATUSES = ["RESEARCH", "CANDIDATE", "VALIDATED", "PAPER", "LIVE", "REJECTED"]

SETUP_CATEGORIES = [
    "Trend Following", "Trend Pullback", "Breakout", "Liquidity Sweep",
    "FVG", "Momentum", "Mean Reversion", "Volatility Expansion", "Session Breakout",
]


@dataclass
class SetupSpec:
    setup_id: str
    market: str          # "crypto" | "gold"
    category: str        # one of SETUP_CATEGORIES
    status: str           # one of SETUP_STATUSES
    entry_point: str       # dotted path to the source function, for traceability
    evidence: str            # doc that justifies `status`
    scannable: bool = False
    detect_fn: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = field(default=None, repr=False)


def _fvg_detect(m15: pd.DataFrame) -> pd.DataFrame:
    from src.scanner.setups.fvg import detect
    return detect(m15)


def _liquidity_sweep_detect(m15: pd.DataFrame) -> pd.DataFrame:
    from src.scanner.setups.liquidity_sweep import detect
    return detect(m15)


def _choch_detect(m15: pd.DataFrame) -> pd.DataFrame:
    from src.scanner.setups.choch import detect
    return detect(m15)


REGISTRY: list[SetupSpec] = [
    SetupSpec(
        setup_id="eth_v0_ema_pullback", market="crypto", category="Trend Pullback",
        status="LIVE", entry_point="src.strategy.v0_rules.generate_v0_signals",
        evidence="docs/HANDOFF.md",
    ),
    SetupSpec(
        setup_id="xrp_v0_ema_pullback", market="crypto", category="Trend Pullback",
        status="PAPER", entry_point="src.strategy.v0_rules.generate_v0_signals",
        evidence="CLAUDE.md",
    ),
    SetupSpec(
        setup_id="crypto_donchian_breakout", market="crypto", category="Breakout",
        status="REJECTED", entry_point="src.strategy.breakout.generate_breakout_signals",
        evidence="docs/FINDINGS.md",
    ),
    SetupSpec(
        setup_id="crypto_mean_reversion", market="crypto", category="Mean Reversion",
        status="REJECTED", entry_point="src.strategy.mean_reversion.generate_mean_reversion_signals",
        evidence="docs/FINDINGS.md",
    ),
    SetupSpec(
        setup_id="gold_r1_orb", market="gold", category="Breakout",
        status="REJECTED", entry_point="src.strategy.gold_orb.generate_orb_signals",
        evidence="docs/research/GOLD_HANDOFF.md",
    ),
    SetupSpec(
        setup_id="gold_r2_orb_pullback", market="gold", category="Trend Pullback",
        status="REJECTED", entry_point="src.strategy.gold_orb_pullback.generate_orb_pullback_signals",
        evidence="docs/research/GOLD_HANDOFF.md",
    ),
    SetupSpec(
        setup_id="gold_r5_dxy_filter", market="gold", category="Trend Following",
        status="REJECTED", entry_point="src.strategy.gold_r5_dxy_filter.generate_r5_signals",
        evidence="docs/research/GOLD_HANDOFF.md",
    ),
    SetupSpec(
        setup_id="gold_r8_liquidation_reversal", market="gold", category="Mean Reversion",
        status="REJECTED", entry_point="src.strategy.gold_r8_liquidation_reversal.generate_r8_signals",
        evidence="docs/research/GOLD_HANDOFF.md",
    ),
    SetupSpec(
        setup_id="gold_r11_wick_fill", market="gold", category="Mean Reversion",
        status="REJECTED", entry_point="src.strategy.gold_r11_wick_fill.generate_r11_signals",
        evidence="docs/research/GOLD_HANDOFF.md",
    ),
    SetupSpec(
        setup_id="gold_r14_fake_zone", market="gold", category="Liquidity Sweep",
        status="REJECTED", entry_point="src.strategy.gold_r14_fake_zone.generate_r14_signals",
        evidence="docs/research/GOLD_HANDOFF.md",
        scannable=True, detect_fn=_liquidity_sweep_detect,
    ),
    SetupSpec(
        setup_id="gold_r15_choch", market="gold", category="Momentum",
        status="REJECTED", entry_point="src.strategy.gold_r15_choch.compute_choch_events",
        evidence="docs/research/GOLD_HANDOFF.md",
        scannable=True, detect_fn=_choch_detect,
    ),
    SetupSpec(
        setup_id="gold_r17_fvg", market="gold", category="FVG",
        status="REJECTED", entry_point="src.strategy.gold_r17_fvg.generate_r17_signals",
        evidence="docs/research/GOLD_HANDOFF.md",
        scannable=True, detect_fn=_fvg_detect,
    ),
]


def get_setups(
    status: Optional[str] = None,
    category: Optional[str] = None,
    market: Optional[str] = None,
    scannable_only: bool = False,
) -> list[SetupSpec]:
    out = REGISTRY
    if status is not None:
        out = [s for s in out if s.status == status]
    if category is not None:
        out = [s for s in out if s.category == category]
    if market is not None:
        out = [s for s in out if s.market == market]
    if scannable_only:
        out = [s for s in out if s.scannable]
    return out


def sync_registry_to_db(engine) -> int:
    """Write a durable snapshot of REGISTRY to the `setups` table (upsert by
    setup_id) -- groundwork for a later promotion workflow / dashboard, not the
    workflow itself. Returns the number of rows written."""
    from sqlalchemy import delete, insert

    now = datetime.now(timezone.utc)
    rows = [
        {
            "setup_id": s.setup_id, "market": s.market, "category": s.category,
            "status": s.status, "entry_point": s.entry_point, "evidence": s.evidence,
            "updated_at_utc": now,
        }
        for s in REGISTRY
    ]
    with engine.begin() as conn:
        conn.execute(delete(setups_table))
        if rows:
            conn.execute(insert(setups_table), rows)
    return len(rows)
