"""Setup Scanner (docs/XAU_ARCHITECTURE_AUDIT.md P5) -- runs the wired detect_fn
for every registry entry whose status is currently allowed to produce signals.

Not called from any live path as of P5 -- see src/scanner/registry.py's module
docstring.
"""
import pandas as pd

from src.scanner.registry import get_setups


def scan(m15: pd.DataFrame, statuses=("VALIDATED", "PAPER", "LIVE")) -> dict[str, pd.DataFrame]:
    """Run detect_fn for every scannable registry entry whose status is in
    `statuses`. With today's registry, the default `statuses` returns {} --
    nothing gold is VALIDATED yet, and the LIVE/PAPER crypto entries aren't
    wired (see registry.py) -- this is the correct, honest behavior per the
    audit's own risk mitigation (no setup reaches LIVE without VALIDATED
    first), not a bug to "fix" by lowering the bar.
    """
    out = {}
    for setup in get_setups(scannable_only=True):
        if setup.status not in statuses:
            continue
        out[setup.setup_id] = setup.detect_fn(m15)
    return out
