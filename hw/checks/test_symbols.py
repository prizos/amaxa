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

from symbols import (  # noqa: E402
    SymbolNotFound, footprint_pads, symbol_pin_names, symbol_pin_types, symbol_pins,
)

STOCK_FOOTPRINTS = Path("/usr/share/kicad/footprints")


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


def test_mounting_holes_are_not_pads():
    """
    A non-plated hole is not a pad, so it cannot be a pad with no pin.

    Checked against stock KiCad footprints the control board uses rather than
    against this board, because the mistake only shows on parts that have such
    holes: a USB-C receptacle's locating pegs and a Tag-Connect footprint's clip
    holes are numbered "" with a copper layer list, and were counted as pads.
    """
    cases = {
        "Connector.pretty/Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical.kicad_mod":
            {"1", "2", "3", "4", "5", "6"},
        "Connector_USB.pretty/USB_C_Receptacle_HRO_TYPE-C-31-M-12.kicad_mod": None,
    }
    wrong = []
    for relative, expected in cases.items():
        path = STOCK_FOOTPRINTS / relative
        if not path.is_file():
            pytest.fail(f"stock footprint {path} is missing; KiCad 9 ships it")
        pads = footprint_pads(path)
        if "" in pads:
            wrong.append(f"  {relative}: a numberless hole was counted as a pad")
        if expected is not None and pads != expected:
            wrong.append(f"  {relative}: pads {sorted(pads)}, expected {sorted(expected)}")
    assert not wrong, "Mounting holes counted as pads:\n" + "\n".join(wrong)


def test_every_designator_is_one_the_design_chose(design):
    """
    No reference carries SKiDL's collision suffix.

    Two parts asking for the same designator is not an error to SKiDL: it keeps
    one and renames the other by appending `_1`. Nothing says so, the build is
    clean, and the board comes out carrying a reference like `R76_1`.

    Three things then go wrong at once. The reference is not of the form an
    assembly house's position file expects, so the part is a question at the
    factory rather than a placement. The part that kept the name is not the one
    the source asked for, so a comment saying "R76 is the CAN termination" is
    now about a different resistor. And the collision itself is invisible: the
    only trace of it is the suffix.

    cpu1 had two - `R76_1` and `C81_1`. Both came from the same cause, a block
    that hands out references from a running counter meeting a block that
    writes them by hand. A designator is a letter or two and a number, which is
    what this asks for, so it names the whole class rather than those two.
    """
    import re

    wrong = sorted(
        f"  {address}: {part['ref']!r}"
        for address, part in design["parts"].items()
        if not re.fullmatch(r"[A-Z]{1,3}[0-9]+", part["ref"] or "")
    )
    assert not wrong, (
        "References that are not a plain prefix and number - SKiDL renames a "
        "part whose designator was already taken, and this is what that looks "
        "like:\n" + "\n".join(wrong)
    )


def test_no_pin_typed_as_an_output_sits_on_a_supply_rail(design, parts):
    """
    Nothing the netlist calls a driver is wired to a rail.

    `test_power.py` decides which rail holds up a resistor chain by asking
    which parts *drive* the net it starts on, and "drives" is a **pin type**
    rather than a connection. That distinction exists because the earlier
    version asked only whether a part powered from a rail touched the net,
    and charged the 3V3 feedback divider to both rails at once.

    The types come from KiCad's symbol, and a symbol is not always the part.
    This board's CAN transceiver is a TCAN1044V drawn with an SN65HVD230's
    symbol - the same eight pins in the same order, which is why it is usable
    at all - and pin 5 differs: a reference **output** on the part the symbol
    is of, and VIO, a supply **input**, on the part that is fitted. `cpu1.py`
    says so at the wiring. The netlist therefore reports a part that drives
    3V3, and it is the only part on this board that reports driving 3V3 at
    all.

    It changes no answer today, because 3V3 is a declared rail and the rail
    check short-circuits on those before it consults the drivers. That is
    luck, not design: the one mechanism built to stop a connection being
    mistaken for a drive is being fed a lie, on the one kind of net where the
    lie is never read.

    So the assertion is the invariant rather than the symptom - a pin typed
    as an output has no business on a rail, whatever the symbol thinks - and
    a part that genuinely drives a rail would have to say so here.
    """
    rails = {"3V3", "3V3A", "5V", "VREF+"}
    pad_net = {(address, pad): net
               for net, nodes in design["nets"].items()
               for address, pad in nodes}
    # What each part's spec admits its symbol gets wrong, by designator.
    misnamed = {spec.mpn: getattr(spec, "symbol_misnames", {})
                for spec in parts.values()}

    wrong = []
    for address, part in design["parts"].items():
        declared = misnamed.get(part.get("mpn"), {})
        for pad, kind in symbol_pin_types(part["symbol"]).items():
            if kind != "output" or str(pad) in declared:
                continue
            net = pad_net.get((address, str(pad)))
            if net in rails:
                name = symbol_pin_names(part["symbol"]).get(str(pad), pad)
                wrong.append(
                    f"  {address} pin {pad} ({name}) is typed output in "
                    f"{part['symbol']} and sits on {net}")
    assert not wrong, (
        "Pins the netlist calls drivers, wired to rails:\n" + "\n".join(wrong)
        + "\nEither the part really does drive that rail - in which case say "
          "so here - or the symbol is a different part's, and then say **that** "
          "in the spec's `symbol_misnames` so the stand-in is something a "
          "check can read rather than something a reader has to notice."
    )


def test_every_symbol_a_part_says_is_a_stand_in_really_is_one(parts):
    """
    A declared misnaming names a pin that exists and gets it wrong.

    `symbol_misnames` is an exemption, and an exemption nobody revisits is how
    the list grows until it excuses everything. So each entry has to earn its
    place twice: the pin has to be on the symbol at all, and the description
    has to differ from the name the symbol already gives it - which is what
    stops a stand-in declaration surviving a swap to a symbol that is right.
    """
    problems = []
    for name, spec in sorted(parts.items()):
        declared = getattr(spec, "symbol_misnames", {})
        if not declared:
            continue
        names = symbol_pin_names(spec.symbol)
        for pad, says in sorted(declared.items()):
            if pad not in names:
                problems.append(f"  {name}: pin {pad} is not on {spec.symbol}")
            elif names[pad].lower() in says.lower().split(",")[0]:
                problems.append(
                    f"  {name}: pin {pad} is called {names[pad]!r} on "
                    f"{spec.symbol} and the spec says {says!r} - if the symbol "
                    f"is right, the exemption is not needed")
    assert not problems, (
        "Stand-in declarations that no longer describe their symbol:\n"
        + "\n".join(problems)
    )
