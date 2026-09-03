"""Scanner adapter for gold_r15_choch (REJECTED, docs/research/GOLD_HANDOFF.md) --
wraps src.features.structure.compute_market_structure (the causal-safe detector
lifted in P3), NOT the falsified generate_r15_signals SL/TP/session logic.
Kept scannable to prove the scanner plumbing works end-to-end; not a live/paper
signal source.
"""
import pandas as pd

from src.features.structure import compute_market_structure


def detect(m15: pd.DataFrame) -> pd.DataFrame:
    """Signal fires on the bar a CHoCH (change of character) is confirmed.
    +1 = CHoCH up (structure flipped bullish), -1 = CHoCH down.
    """
    state = compute_market_structure(m15)
    signal = state["choch_dir"].map({"UP": 1, "DOWN": -1}).fillna(0)
    return pd.DataFrame({"time_utc": state["time_utc"], "signal": signal})
