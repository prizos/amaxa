"""
How a board describes the parts it buys: `PartSpec`, and the tolerance helpers.

Every board's `parts.py` is a list of these. It is deliberately free of any
SKiDL import, so a part list stays readable, diffable and checkable without a
design tool in the loop — the checks load it with the system Python.
"""

from dataclasses import dataclass, field


# --- how a tolerance is written ---------------------------------------------


def pm(nominal: float, fraction: float) -> tuple[float, float]:
    """A nominal value with a symmetric tolerance: `pm(2200, 0.01)` is 2.2k ±1%."""
    return nominal * (1 - fraction), nominal * (1 + fraction)


def exact(value: float) -> tuple[float, float]:
    """A single figure from a datasheet, with no stated spread."""
    return value, value


def between(low: float, high: float) -> tuple[float, float]:
    """A range the datasheet states outright, such as a threshold voltage."""
    return low, high


@dataclass(frozen=True)
class PartSpec:
    """One purchasable part, or one deliberately unpurchased piece of copper."""

    symbol: str
    """KiCad symbol, `Library:Name`. Its pin numbers must match the footprint."""

    footprint: str
    """`<LIB>:<NAME>`, resolved against `parts/<LIB>/<NAME>.kicad_mod`."""

    prefix: str
    """Designator prefix we expect KiCad's symbol to assign."""

    manufacturer: str
    mpn: str

    lcsc: str | None
    """Supplier code, or None for something we deliberately do not buy."""

    value: str
    """What goes in the BOM's Value column and on the silkscreen."""

    params: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Datasheet figures the checks and simulations reason about, in SI units."""


def collect(namespace: dict) -> dict[str, PartSpec]:
    """Every `PartSpec` in a module's globals, by name. A board's `ALL`."""
    return {name: value for name, value in namespace.items() if isinstance(value, PartSpec)}
