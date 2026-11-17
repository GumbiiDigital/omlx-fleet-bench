"""Small statistics helpers shared by the reports and the charts."""

from __future__ import annotations

from math import sqrt
from statistics import mean
from typing import Sequence, Tuple

# Two-sided 95% normal quantile.
Z_95 = 1.959963984540054


def spread(values: Sequence[float]) -> float:
    """Range over mean, as a fraction. 0.0 for fewer than two values or a zero mean."""
    if len(values) < 2:
        return 0.0
    centre = mean(values)
    if centre == 0:
        return 0.0
    return (max(values) - min(values)) / centre


def wilson_interval(successes: int, total: int, z: float = Z_95) -> Tuple[float, float]:
    """Wilson score interval for a proportion, as fractions in [0, 1].

    Used for accuracy on a fixed question set. It behaves near 0% and 100%, where the
    plain normal interval runs past the ends.
    """
    if total <= 0:
        raise ValueError("total must be positive")
    if not 0 <= successes <= total:
        raise ValueError("successes must be between 0 and total")
    p = successes / total
    z2 = z * z
    denom = 1 + z2 / total
    centre = (p + z2 / (2 * total)) / denom
    half = z * sqrt(p * (1 - p) / total + z2 / (4 * total * total)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)
