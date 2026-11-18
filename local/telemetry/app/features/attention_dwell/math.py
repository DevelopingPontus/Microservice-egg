"""Pure math functions for attentional Shannon entropy."""

import math
from collections.abc import Mapping


def compute_shannon_entropy(dwell_distribution: Mapping[str, float]) -> float:
    """Compute Shannon entropy in bits (log2 base) over active window dwell times."""
    total_dwell = sum(dwell_distribution.values())
    if total_dwell <= 0.0 or len(dwell_distribution) <= 1:
        return 0.0

    entropy_bits = 0.0
    for seconds in dwell_distribution.values():
        if seconds > 0.0:
            p = seconds / total_dwell
            entropy_bits -= p * math.log2(p)

    return round(max(0.0, entropy_bits), 4)
