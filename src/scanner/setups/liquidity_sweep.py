"""Scanner adapter for gold_r14_fake_zone (REJECTED, docs/research/GOLD_HANDOFF.md) --
wraps src.features.structure.compute_liquidity_sweep_state (the causal-safe
detector lifted in P3), NOT the falsified generate_r14_signals SL/TP/session
logic. Kept scannable to prove the scanner plumbing works end-to-end; not a
live/paper signal source.
"""
import pandas as pd

from src.features.structure import compute_liquidity_sweep_state


def detect(m15: pd.DataFrame) -> pd.DataFrame:
    """Signal fires on the bar a fake-break/liquidity sweep is confirmed.
    +1 = fade a fake break below a swing low (long bias), -1 = fade a fake
    break above a swing high (short bias) -- matches sweep_fired_dir's
    DOWN/UP convention in structure.py.
    """
    state = compute_liquidity_sweep_state(m15)
    signal = state["sweep_fired_dir"].map({"DOWN": 1, "UP": -1}).fillna(0)
    return pd.DataFrame({"time_utc": state["time_utc"], "signal": signal})
