"""Scanner adapter for gold_r17_fvg (REJECTED, docs/research/GOLD_HANDOFF.md) --
wraps src.features.structure.compute_fvg_state (the causal-safe detector lifted
in P3), NOT the falsified generate_r17_signals SL/TP/session logic. Kept
scannable to prove the scanner plumbing works end-to-end; not a live/paper
signal source.
"""
import pandas as pd

from src.features.structure import compute_fvg_state


def detect(m15: pd.DataFrame) -> pd.DataFrame:
    """Signal fires on the bar an FVG first becomes active (gap just formed)."""
    state = compute_fvg_state(m15)
    bull_new = state["bull_gap_active"] & (state["bars_since_bull_gap"] == 0)
    bear_new = state["bear_gap_active"] & (state["bars_since_bear_gap"] == 0)
    signal = pd.Series(0, index=state.index)
    signal[bull_new] = 1
    signal[bear_new] = -1
    return pd.DataFrame({"time_utc": state["time_utc"], "signal": signal})
