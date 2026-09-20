"""
IEC 60063's preferred values, for checks that ask "is this the right part".

A capacitor cannot be any value wanted. When a design solves for one - a
crystal's load, a divider's ratio - the answer is a real number and the part
is the nearest thing a distributor stocks, so "the right value" means the
closest the series offers and nothing else. That is a published standard
rather than a belief about any board, which is why it lives here.
"""

import math

E24 = (10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30, 33, 36,
       39, 43, 47, 51, 56, 62, 68, 75, 82, 91)


def e24_values(near: float) -> list[float]:
    """
    Every E24 value within a decade either side of `near`, in `near`'s units.

    Either side matters. A window that starts at the decade below and runs
    upward leaves a value sitting on a decade boundary with no candidate
    beneath it, and "no value gets closer" is then only tested one way.
    """
    if near <= 0.0:
        raise ValueError(f"no series around {near:g}")
    decade = 10.0 ** math.floor(math.log10(near))
    return [v * decade * scale / 100.0 for scale in (1, 10, 100, 1000) for v in E24]


def closest(near: float, score) -> float:
    """The E24 value around `near` that `score` likes best, smallest first."""
    return min(e24_values(near), key=score)
