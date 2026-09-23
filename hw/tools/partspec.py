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

    symbol_misnames: dict[str, str] = field(default_factory=dict)
    """
    Pin number -> what that pin really is, where the symbol is a stand-in.

    A symbol is a drawing of *a* part, and sometimes the nearest drawing is of
    a different one: the same package, the same pin order, one or two pins
    that mean something else. `hw/cpu1` borrows a symbol three times and only
    one of those borrowings changes what a pin **is** - the octal buffer's
    numbering differs from TI's by one and the latch's family differs with the
    pinout intact, and neither of those is a fact any check reads. This is for
    the kind that is.

    What made it worth writing down is that the netlist's pin **types** come
    from the symbol, and `test_power.py` uses those types to tell a part that
    drives a net from a part that merely sits on it. A stand-in whose pin 5 is
    a reference *output* on the drawn part and a supply *input* on the fitted
    one makes the netlist report a driver that does not exist - so the one
    mechanism built to stop a connection being read as a drive is the
    mechanism a stand-in breaks first.

    Declaring it here makes the stand-in machine-readable rather than a thing
    a reader has to notice, and
    `checks/test_symbols.py::test_no_pin_typed_as_an_output_sits_on_a_supply_rail`
    reads it. The entries cannot rot: a pin declared here must exist on the
    symbol, and the text must differ from the name the symbol gives it.
    """


def collect(namespace: dict) -> dict[str, PartSpec]:
    """Every `PartSpec` in a module's globals, by name. A board's `ALL`."""
    return {name: value for name, value in namespace.items() if isinstance(value, PartSpec)}
