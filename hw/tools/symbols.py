"""
Read KiCad symbol and footprint libraries, just enough to compare their pins.

A symbol says a part has a pin numbered 3 called `D`; a footprint says the
package has a pad numbered 3. Nothing in the toolchain checks that those two
agree — a design will happily build, route and pass DRC with a part wired to
the wrong leg, because every layer downstream trusts the pairing it was given.

Deliberately dependency-free so it can run under the system Python, like
everything else in `tools/`.
"""

import re
from pathlib import Path

KICAD_SYMBOL_DIR = Path("/usr/share/kicad/symbols")


class SymbolNotFound(Exception):
    """Named symbol is not in the library, or the library does not exist."""


def _block(text: str, start: int) -> str:
    """The balanced s-expression beginning at `start`."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _find_symbol(library_text: str, name: str) -> str:
    match = re.search(r'\(symbol "' + re.escape(name) + r'"', library_text)
    if not match:
        raise SymbolNotFound(name)
    return _block(library_text, match.start())


def symbol_pins(reference: str, library_dir: Path | None = None) -> set[str]:
    """
    The pin *numbers* of a symbol named `Library:Symbol`.

    Follows `extends`, because most device-specific symbols — `2N7002`, say —
    carry no pins of their own and inherit them from a generic parent.
    """
    library_dir = library_dir or KICAD_SYMBOL_DIR
    library_name, _, symbol_name = reference.partition(":")
    if not symbol_name:
        raise SymbolNotFound(f"{reference!r} is not of the form Library:Symbol")

    path = library_dir / f"{library_name}.kicad_sym"
    if not path.is_file():
        raise SymbolNotFound(f"no symbol library {path}")

    text = path.read_text()
    seen: set[str] = set()
    while symbol_name not in seen:
        seen.add(symbol_name)
        block = _find_symbol(text, symbol_name)
        pins = set(re.findall(r'\(number "([^"]+)"', block))
        if pins:
            return pins
        parent = re.search(r'\(extends "([^"]+)"', block)
        if not parent:
            return set()
        symbol_name = parent.group(1)
    raise SymbolNotFound(f"{reference}: extends forms a loop")


def symbol_pin_names(reference: str, library_dir: Path | None = None) -> dict[str, str]:
    """
    Pin number -> pin name, for a symbol named `Library:Symbol`.

    What a pin is *for*, which the netlist does not record: it has nodes on pin
    numbers, and a check that wants to know whether the receiver enable is tied
    active has otherwise to be told that the receiver enable is pin 2. Told, it
    keeps saying the same thing after the pin moves.

    Names are as KiCad writes them, overbars and all: `~{RE}`, not `RE`.
    """
    library_dir = library_dir or KICAD_SYMBOL_DIR
    library_name, _, symbol_name = reference.partition(":")
    if not symbol_name:
        raise SymbolNotFound(f"{reference!r} is not of the form Library:Symbol")

    path = library_dir / f"{library_name}.kicad_sym"
    if not path.is_file():
        raise SymbolNotFound(f"no symbol library {path}")

    text = path.read_text()
    seen: set[str] = set()
    while symbol_name not in seen:
        seen.add(symbol_name)
        block = _find_symbol(text, symbol_name)
        names = {}
        for chunk in block.split("(pin ")[1:]:
            name = re.search(r'\(name "([^"]*)"', chunk)
            number = re.search(r'\(number "([^"]+)"', chunk)
            if name and number:
                names[number.group(1)] = name.group(1)
        if names:
            return names
        parent = re.search(r'\(extends "([^"]+)"', block)
        if not parent:
            return {}
        symbol_name = parent.group(1)
    raise SymbolNotFound(f"{reference}: extends forms a loop")


def footprint_pads(path: Path) -> set[str]:
    """
    The pad *numbers* of a footprint that carry copper.

    Numbers repeat legitimately — a tactile switch has four holes numbered
    1, 1, 2, 2 for two poles, and a SOT-223 tab shares its number with the pin
    it is bonded to — so this is a set, not a count.

    Non-plated holes are not pads. A USB-C receptacle's locating pegs and a
    Tag-Connect footprint's clip holes are `np_thru_hole` with an empty number,
    and their layer list still says `*.Cu`, so testing for copper alone counted
    each one as a pad with no pin.
    """
    text = path.read_text()
    pads = set()
    for match in re.finditer(r'\(pad "([^"]*)" (\w+)', text):
        if not is_electrical_pad(match.group(1), match.group(2)):
            continue
        block = _block(text, match.start())
        if "Cu" in block:
            pads.add(match.group(1))
    return pads


def is_electrical_pad(number: str, kind: str) -> bool:
    """Whether a footprint pad can carry a net: not a mounting or locating hole."""
    return kind != "np_thru_hole" and number != ""


def symbol_description(reference: str, library_dir: Path | None = None) -> str:
    """
    A symbol's Description property, for a symbol named `Library:Symbol`.

    KiCad writes what a part *is* here - "N-Channel MOSFET", "P-MOSFET
    transistor" - and for a discrete transistor that sentence is the only
    machine-readable statement of its channel. A part-numbered symbol like
    2N7002 spells its pins G, S and D and says nothing else about polarity;
    the generic `Q_NMOS_GSD` spells the order into its own name and not the
    pin names. This reads the one field both of them fill in.
    """
    library_dir = library_dir or KICAD_SYMBOL_DIR
    library_name, _, symbol_name = reference.partition(":")
    path = library_dir / f"{library_name}.kicad_sym"
    if not path.is_file():
        raise SymbolNotFound(f"no symbol library {path}")

    text = path.read_text()
    seen: set[str] = set()
    while symbol_name not in seen:
        seen.add(symbol_name)
        block = _find_symbol(text, symbol_name)
        found = re.search(r'\(property "Description" "([^"]*)"', block)
        if found and found.group(1):
            return found.group(1)
        parent = re.search(r'\(extends "([^"]+)"', block)
        if not parent:
            return ""
        symbol_name = parent.group(1)
    raise SymbolNotFound(f"{reference}: extends forms a loop")
