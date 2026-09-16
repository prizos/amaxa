"""
Checks that each part's symbol and its footprint agree about pin numbering.

Nothing else in the toolchain does this. A symbol says the part has a pin
numbered 3 called `D`; a footprint says the package has a pad numbered 3. If
those disagree, the design builds, routes and passes DRC with a transistor
wired to the wrong leg, because every layer downstream trusts the pairing it
was handed.

The port that introduced these checks also found the bug that motivates them:
the previous design source named `Device:Q_NMOS_GSD` and `Device:Q_PMOS_GSD`,
neither of which exists in any KiCad library. It never noticed, because it
never resolved symbols at all.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

HW_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HW_DIR / "tools"))

from symbols import SymbolNotFound, footprint_pads, symbol_pins  # noqa: E402


@pytest.fixture(scope="session")
def parts(board_dir):
    """The board's part list, loaded from its own `parts.py`."""
    path = board_dir / "parts.py"
    if not path.is_file():
        pytest.skip(f"no {path}; this board does not define parts in Python yet")
    spec = importlib.util.spec_from_file_location(f"{board_dir.name}_parts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ALL


def footprint_path(board_dir: Path, footprint: str) -> Path:
    library, _, name = footprint.partition(":")
    return board_dir / "parts" / library / f"{name}.kicad_mod"


def test_every_symbol_exists(parts):
    """
    A part naming a symbol that is not in any library.

    This is not a hypothetical: two of ours did, for months.
    """
    missing = []
    for name, part in sorted(parts.items()):
        try:
            symbol_pins(part.symbol)
        except SymbolNotFound as exc:
            missing.append(f"  {name}: {part.symbol!r} — {exc}")
    assert not missing, "Parts naming symbols that do not exist:\n" + "\n".join(missing)


def test_every_footprint_file_exists(parts, board_dir):
    """The footprint a part names is a file in our own parts tree."""
    missing = [
        f"  {name}: {part.footprint} -> {footprint_path(board_dir, part.footprint)}"
        for name, part in sorted(parts.items())
        if not footprint_path(board_dir, part.footprint).is_file()
    ]
    assert not missing, "Footprints named but not present:\n" + "\n".join(missing)


def test_symbol_pins_match_footprint_pads(parts, board_dir):
    """
    Every symbol pin number has a pad of that number, and vice versa.

    Compared as sets, because pad numbers legitimately repeat: a tactile switch
    has four holes numbered 1, 1, 2, 2 for its two poles, and a SOT-223's tab
    shares a number with the pin it is bonded to.
    """
    wrong = []
    for name, part in sorted(parts.items()):
        path = footprint_path(board_dir, part.footprint)
        if not path.is_file():
            continue  # its own check covers this
        try:
            pins = symbol_pins(part.symbol)
        except SymbolNotFound:
            continue  # likewise
        pads = footprint_pads(path)
        if pins != pads:
            wrong.append(
                f"  {name}: symbol {part.symbol} has pins {sorted(pins)}, "
                f"footprint {part.footprint} has pads {sorted(pads)}"
                + (f"\n      pins with no pad: {sorted(pins - pads)}" if pins - pads else "")
                + (f"\n      pads with no pin: {sorted(pads - pins)}" if pads - pins else "")
            )
    assert not wrong, (
        "Symbols and footprints disagree about pin numbering. A part wired this "
        "way passes every other check and arrives connected wrongly:\n"
        + "\n".join(wrong)
    )


def test_every_purchasable_part_has_a_supplier_code(parts):
    """
    A part with no supplier code is one nobody can order.

    `lcsc=None` says so deliberately — bare copper, a mounting hole — and those
    are excluded from the BOM rather than sitting on it unorderable.
    """
    blank = [
        f"  {name}: lcsc={part.lcsc!r}"
        for name, part in sorted(parts.items())
        if part.lcsc is not None and not part.lcsc.strip()
    ]
    assert not blank, (
        "Parts with an empty supplier code. Use None to mean 'deliberately not "
        "purchased'; an empty string means someone meant to fill it in:\n"
        + "\n".join(blank)
    )
