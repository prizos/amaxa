"""
Read the specs atopile prints, as numbers.

The build reports every parameter as a string in one of four shapes: a single
value `125mW`, a tolerance `680Ω ±1%`, a range `2-2.4V` or `90-110nF`, and the
unconstrained `{ℝ+}A` for one that was never given a value. This turns them
into a plain (low, high) pair in SI units.

Shared by the design checks and the simulation runner, and deliberately free of
any dependency beyond the standard library, because the simulation runner is
run by the system Python rather than the atopile virtualenv.
"""

import re

_PREFIX = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3,
    "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9,
}
_UNITS = ("Ω", "V", "A", "W", "F", "H", "s", "cd", "Hz")
_NUMBER = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


class UnconstrainedSpec(Exception):
    """The parameter was never given a value, so nothing can be computed from it."""


def _magnitude(text: str, fallback_suffix: str = "") -> float:
    """Turn `680Ω`, `125mW`, `2.4` (with a fallback suffix) into a number in SI units."""
    text = text.strip()
    match = re.fullmatch(rf"({_NUMBER})\s*(.*)", text)
    if not match:
        raise ValueError(f"cannot read a number from {text!r}")
    value, suffix = float(match.group(1)), match.group(2).strip() or fallback_suffix

    for unit in _UNITS:
        if suffix.endswith(unit):
            prefix = suffix[: -len(unit)]
            if prefix in _PREFIX:
                return value * _PREFIX[prefix]
            break
    if suffix in _PREFIX:  # bare prefix, no unit
        return value * _PREFIX[suffix]
    raise ValueError(f"unknown unit in {text!r}")


def _suffix_of(text: str) -> str:
    match = re.fullmatch(rf"{_NUMBER}\s*(.*)", text.strip())
    return match.group(1).strip() if match else ""


def parse_spec(spec: str | None) -> tuple[float, float]:
    """
    An atopile spec string as an inclusive (low, high) range in SI units.

    Handles the four shapes it emits: a single value `125mW`, a tolerance
    `680Ω ±1%`, a range `2-2.4V` or `90-110nF`, and the unconstrained `{ℝ+}A`.
    Raises UnconstrainedSpec for the last, because a check that silently treats
    "never specified" as "zero to infinity" passes for the wrong reason.
    """
    if spec is None or "ℝ" in spec or spec == "<empty>":
        raise UnconstrainedSpec(f"no usable value: {spec!r}")

    text = spec.strip()

    tolerance = re.fullmatch(rf"(.+?)\s*±\s*({_NUMBER})\s*%", text)
    if tolerance:
        centre = _magnitude(tolerance.group(1))
        fraction = float(tolerance.group(2)) / 100.0
        return centre * (1 - fraction), centre * (1 + fraction)

    # A range: the unit may appear only on the upper bound, as in `2-2.4V`.
    range_match = re.fullmatch(rf"({_NUMBER}\s*\S*?)\s*-\s*({_NUMBER}\s*\S*)", text)
    if range_match:
        low_text, high_text = range_match.group(1), range_match.group(2)
        high = _magnitude(high_text)
        low = _magnitude(low_text, fallback_suffix=_suffix_of(high_text))
        return low, high

    single = _magnitude(text)
    return single, single


