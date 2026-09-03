"""Deterministic Setup Quality Scorecard -- docs/XAU_ARCHITECTURE_AUDIT.md §16.

Six Python-owned channels only (Trend/Structure/Momentum/Volatility/Session/Risk,
§16.2) -- Macro is out of scope here: §15 item 10 already cut the news/calendar
source, so src/ai/analyst.py's LLM call can only veto and narrate, it contributes
no score. Final Score is an EQUAL-WEIGHT mean of the 6 channels, deliberately --
§16.5 flags hand-tuned weights as exactly the kind of free-parameter risk that
killed the LightGBM gate (AUC 0.497, docs/FINDINGS.md), so this uses the one
weighting scheme that introduces no new tunable parameter.

Every channel formula below is a documented design choice made this session, NOT
derived from a spec (the audit doc says WHO computes each channel and which
features feed it, not the exact formula) -- and NOT yet validated. See
scripts/bucket_test_scorecard.py for the falsification test (§16.6 item 1) that
must pass before any of this is wired into a live/backtest decision path.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.features.engine import build_features
from src.features.structure import _atr

WEAKEST_LINK_THRESHOLD = 50.0
NO_TRADE_THRESHOLD = 60.0
NORMAL_RISK_THRESHOLD = 75.0

CHANNELS = ["trend", "structure", "momentum", "volatility", "session", "risk"]

# Standard XAU session liquidity ranking (London/NY overlap highest, Asia/off
# lowest) -- a domain-knowledge ordering, not backtest-tuned.
_SESSION_SCORE = {"OVERLAP": 95, "LONDON": 90, "NY": 80, "ASIA": 50, "OFF": 30}

# Risk channel target: SL distance in ATR terms closest to this is scored
# highest. 1.5 sits between the crypto V0 SL (2.5x ATR) and the gold
# strategies' tighter multipliers (~0.5-1x k-values) -- a documented midpoint,
# not derived from any of them specifically.
_RISK_IDEAL_SL_ATR = 1.5


@dataclass
class Scorecard:
    trend: float
    structure: float
    momentum: float
    volatility: float
    session: float
    risk: float
    final_score: float
    weakest_link_block: bool


@dataclass
class GateResult:
    decision: str   # "NO_TRADE" | "SMALL_RISK" | "NORMAL_RISK"
    risk_pct: float  # 0.0 | 0.25 | 0.5, per §16.3


def _dir_sign(direction: str) -> int:
    return 1 if direction == "LONG" else -1


def _safe(x, default: float = 50.0) -> float:
    return default if pd.isna(x) else float(x)


def _trend_score(f03_h1_trend_atr, f04_adx14_h1, direction: str) -> float:
    alignment = np.clip(_safe(f03_h1_trend_atr, 0.0) * _dir_sign(direction), -2, 2) / 2
    strength = np.clip(_safe(f04_adx14_h1, 0.0) / 40.0, 0, 1)
    return float(np.clip(50 + 50 * alignment * strength, 0, 100))


def _structure_score(f19_dist_swing_high_atr, f20_dist_swing_low_atr,
                      f21_trend_state, f22_bos_fired, direction: str) -> float:
    dirsign = _dir_sign(direction)
    trend_component = np.clip(
        0.6 * (_safe(f21_trend_state, 0.0) * dirsign) + 0.4 * (_safe(f22_bos_fired, 0.0) * dirsign),
        -1, 1,
    )
    room = _safe(f19_dist_swing_high_atr, 0.0) if direction == "LONG" else _safe(f20_dist_swing_low_atr, 0.0)
    room_component = np.clip(room / 3.0, -1, 1)
    return float(np.clip(50 + 25 * trend_component + 25 * room_component, 0, 100))


def _momentum_score(f05_logret_4, f06_logret_12, direction: str) -> float:
    dirsign = _dir_sign(direction)
    raw = 0.5 * (_safe(f05_logret_4, 0.0) * dirsign) + 0.5 * (_safe(f06_logret_12, 0.0) * dirsign)
    return float(np.clip(50 + 50 * np.clip(raw / 0.01, -1, 1), 0, 100))


def _volatility_score(f08_atr_percentile) -> float:
    return float(np.clip(100 * _safe(f08_atr_percentile, 0.5), 0, 100))


def _session_score(session) -> float:
    return float(_SESSION_SCORE.get(session, 50))


def _risk_score(sl_distance: float, atr_at_entry: float) -> float:
    if not atr_at_entry or pd.isna(atr_at_entry) or atr_at_entry <= 0 or pd.isna(sl_distance):
        return 50.0
    sl_atr = sl_distance / atr_at_entry
    return float(np.clip(100 - 20 * abs(sl_atr - _RISK_IDEAL_SL_ATR), 0, 100))


def compute_scorecard(
    features_row,
    direction: str,
    sl_distance: float,
    atr_at_entry: float,
) -> Scorecard:
    """features_row: a row (pd.Series) from src.features.engine.build_features's
    output -- already bar-shifted, so this reflects only data available at the
    decision point. direction: "LONG" | "SHORT". sl_distance/atr_at_entry: price
    units, from the trade's own entry (sl_distance = |entry - sl_price|,
    atr_at_entry = ATR14 on the entry bar's m15 series -- NOT from features_row,
    which only carries the shifted f* columns).
    """
    trend = _trend_score(features_row.get("f03_h1_trend_atr"), features_row.get("f04_adx14_h1"), direction)
    structure = _structure_score(
        features_row.get("f19_dist_swing_high_atr"), features_row.get("f20_dist_swing_low_atr"),
        features_row.get("f21_trend_state"), features_row.get("f22_bos_fired"), direction,
    )
    momentum = _momentum_score(features_row.get("f05_logret_4"), features_row.get("f06_logret_12"), direction)
    volatility = _volatility_score(features_row.get("f08_atr_percentile"))
    session = _session_score(features_row.get("session"))
    risk = _risk_score(sl_distance, atr_at_entry)

    channels = [trend, structure, momentum, volatility, session, risk]
    final_score = float(np.mean(channels))
    weakest_link_block = any(c < WEAKEST_LINK_THRESHOLD for c in channels)

    return Scorecard(
        trend=trend, structure=structure, momentum=momentum, volatility=volatility,
        session=session, risk=risk, final_score=final_score,
        weakest_link_block=weakest_link_block,
    )


def gate(scorecard: Scorecard) -> GateResult:
    """§16.3: <60 or weakest-link block -> NO_TRADE; 60-75 -> small risk (0.25%);
    >75 -> normal risk (0.5%, per §11 risk_per_trade)."""
    if scorecard.weakest_link_block or scorecard.final_score < NO_TRADE_THRESHOLD:
        return GateResult(decision="NO_TRADE", risk_pct=0.0)
    if scorecard.final_score <= NORMAL_RISK_THRESHOLD:
        return GateResult(decision="SMALL_RISK", risk_pct=0.25)
    return GateResult(decision="NORMAL_RISK", risk_pct=0.5)


def compute_scorecard_batch(m15: pd.DataFrame, h1: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """trades: a labeled/costed trades DataFrame (src.backtest.gold_harness output
    shape) with at least time_utc, action, sl_distance. Returns `trades` with one
    column per Scorecard field appended (trend/structure/.../final_score/
    weakest_link_block), computed from the SAME m15/h1 the trades were generated
    from -- time_utc is matched exactly (trade entries are m15 bar timestamps
    from this same frame), no lookahead beyond what build_features already
    guarantees (every f* column is already shifted by 1 bar).
    """
    features = build_features(m15, h1)
    m15_atr = m15[["time_utc"]].copy()
    m15_atr["atr14"] = _atr(m15, 14)

    lookup = features.merge(m15_atr, on="time_utc", how="left")
    joined = trades.merge(lookup, on="time_utc", how="left", suffixes=("", "_feat"))

    records = []
    for _, row in joined.iterrows():
        sc = compute_scorecard(row, row["action"], row["sl_distance"], row["atr14"])
        records.append(sc.__dict__)

    scorecard_df = pd.DataFrame(records, index=trades.index)
    return pd.concat([trades.reset_index(drop=True), scorecard_df.reset_index(drop=True)], axis=1)
